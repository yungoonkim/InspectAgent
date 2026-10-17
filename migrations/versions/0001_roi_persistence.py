from alembic import op
import sqlalchemy as sa


revision = "0001_roi_persistence"
down_revision = None
branch_labels = None
depends_on = None
SCOPE = ("video_id", "source_revision", "product_id", "source_width", "source_height")


def scope_columns(primary=False):
    return [sa.Column("video_id", sa.String(10), nullable=False, primary_key=primary),
            sa.Column("source_revision", sa.String(64), nullable=False, primary_key=primary),
            sa.Column("product_id", sa.String(64), nullable=False, primary_key=primary),
            sa.Column("source_width", sa.Integer, nullable=False, primary_key=primary),
            sa.Column("source_height", sa.Integer, nullable=False, primary_key=primary)]


def upgrade():
    op.create_table("roi_presets", sa.Column("roi_config_id", sa.String(36), primary_key=True),
                    *scope_columns(), sa.Column("head_version", sa.Integer, nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                    sa.UniqueConstraint("roi_config_id", *SCOPE, name="uq_roi_preset_scope"),
                    sa.CheckConstraint("source_width > 0 AND source_height > 0 AND head_version > 0", name="ck_roi_source"))
    op.create_table("roi_preset_versions",
                    sa.Column("roi_config_id", sa.String(36), primary_key=True),
                    sa.Column("version", sa.Integer, primary_key=True),
                    *(sa.Column(name, sa.Integer, nullable=False) for name in ("x", "y", "width", "height")),
                    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                    sa.ForeignKeyConstraint(["roi_config_id"], ["roi_presets.roi_config_id"], name="fk_roi_version_preset"),
                    sa.CheckConstraint("version > 0 AND x >= 0 AND y >= 0 AND width > 0 AND height > 0", name="ck_roi_rectangle"))
    op.create_table("roi_approvals", sa.Column("roi_config_id", sa.String(36), primary_key=True),
                    sa.Column("version", sa.Integer, primary_key=True),
                    sa.Column("approved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                    sa.ForeignKeyConstraint(["roi_config_id", "version"],
                                            ["roi_preset_versions.roi_config_id", "roi_preset_versions.version"], name="fk_roi_approval_version"))
    op.create_table("roi_active_bindings", *scope_columns(primary=True),
                    sa.Column("roi_config_id", sa.String(36), nullable=False),
                    sa.Column("version", sa.Integer, nullable=False),
                    sa.Column("binding_revision", sa.Integer, nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                    sa.ForeignKeyConstraint(["roi_config_id", "version"], ["roi_approvals.roi_config_id", "roi_approvals.version"], name="fk_roi_active_approved"),
                    sa.ForeignKeyConstraint(["roi_config_id", *SCOPE],
                                            ["roi_presets.roi_config_id", *(f"roi_presets.{field}" for field in SCOPE)], name="fk_roi_active_scope"),
                    sa.CheckConstraint("binding_revision > 0", name="ck_roi_binding_revision"))
    op.execute("""CREATE FUNCTION roi_reject_history_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'ROI_HISTORY_IMMUTABLE' USING ERRCODE='23514'; END $$""")
    for table in ("roi_preset_versions", "roi_approvals"):
        op.execute(f"CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION roi_reject_history_change()")
    op.execute("""CREATE FUNCTION roi_check_geometry() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE source roi_presets%ROWTYPE;
        BEGIN
            SELECT * INTO STRICT source FROM roi_presets WHERE roi_config_id=NEW.roi_config_id;
            IF NEW.x::bigint + NEW.width > source.source_width OR NEW.y::bigint + NEW.height > source.source_height
                OR NEW.version <> source.head_version THEN
                RAISE EXCEPTION 'ROI_GEOMETRY_OR_VERSION_INVALID' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("CREATE TRIGGER geometry_guard BEFORE INSERT ON roi_preset_versions FOR EACH ROW EXECUTE FUNCTION roi_check_geometry()")
    op.execute("""CREATE FUNCTION roi_check_preset_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (to_jsonb(NEW) - 'head_version') IS DISTINCT FROM (to_jsonb(OLD) - 'head_version')
                OR NEW.head_version <> OLD.head_version + 1 THEN
                RAISE EXCEPTION 'ROI_PRESET_SCOPE_IMMUTABLE' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute("CREATE TRIGGER preset_scope_guard BEFORE UPDATE ON roi_presets FOR EACH ROW EXECUTE FUNCTION roi_check_preset_update()")


def downgrade():
    raise RuntimeError("ROI_HISTORY_PRESERVING_DOWNGRADE_NOT_SUPPORTED")
