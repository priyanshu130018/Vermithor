"""Initial database schema for Vermithor

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector

# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create pgvector extension if on PostgreSQL
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. metric_observations
    op.create_table(
        'metric_observations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('observation_id', sa.String(length=255), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('service', sa.String(length=128), nullable=False),
        sa.Column('environment', sa.String(length=64), nullable=False),
        sa.Column('metric_name', sa.String(length=128), nullable=False),
        sa.Column('metric_value', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('labels', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('observation_id')
    )
    op.create_index('ix_metric_observations_environment', 'metric_observations', ['environment'], unique=False)
    op.create_index('ix_metric_observations_metric_name', 'metric_observations', ['metric_name'], unique=False)
    op.create_index('ix_metric_observations_observation_id', 'metric_observations', ['observation_id'], unique=False)
    op.create_index('ix_metric_observations_service', 'metric_observations', ['service'], unique=False)
    op.create_index('ix_metric_observations_timestamp', 'metric_observations', ['timestamp'], unique=False)

    # 3. anomaly_results
    op.create_table(
        'anomaly_results',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('observation_id', sa.String(length=255), nullable=False),
        sa.Column('detector', sa.String(length=64), nullable=False),
        sa.Column('detector_version', sa.String(length=32), nullable=False, server_default='1.0'),
        sa.Column('anomaly_score', sa.Float(), nullable=False),
        sa.Column('is_anomaly', sa.Boolean(), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False),
        sa.Column('expected_value', sa.Float(), nullable=True),
        sa.Column('deviation', sa.Float(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('observation_id', 'detector', name='uq_anomaly_results_obs_detector')
    )
    op.create_index('ix_anomaly_results_created_at', 'anomaly_results', ['created_at'], unique=False)
    op.create_index('ix_anomaly_results_detector', 'anomaly_results', ['detector'], unique=False)
    op.create_index('ix_anomaly_results_is_anomaly', 'anomaly_results', ['is_anomaly'], unique=False)
    op.create_index('ix_anomaly_results_observation_id', 'anomaly_results', ['observation_id'], unique=False)
    op.create_index('ix_anomaly_results_severity', 'anomaly_results', ['severity'], unique=False)

    # 4. events (ingestion)
    op.create_table(
        'events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.String(length=255), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('service', sa.String(length=128), nullable=False),
        sa.Column('environment', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('trace_id', sa.String(length=255), nullable=True),
        sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processing_status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('processing_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id')
    )
    op.create_index('ix_events_environment', 'events', ['environment'], unique=False)
    op.create_index('ix_events_event_id', 'events', ['event_id'], unique=False)
    op.create_index('ix_events_event_type', 'events', ['event_type'], unique=False)
    op.create_index('ix_events_processing_status', 'events', ['processing_status'], unique=False)
    op.create_index('ix_events_service', 'events', ['service'], unique=False)
    op.create_index('ix_events_severity', 'events', ['severity'], unique=False)
    op.create_index('ix_events_trace_id', 'events', ['trace_id'], unique=False)

    # 5. correlation_groups
    op.create_table(
        'correlation_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('group_key', sa.String(length=64), nullable=False),
        sa.Column('environment', sa.String(length=64), nullable=False),
        sa.Column('primary_service', sa.String(length=128), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('correlation_score', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='CANDIDATE', nullable=False),
        sa.Column('reasons', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('incident_key', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_key')
    )
    op.create_index('ix_correlation_groups_correlation_score', 'correlation_groups', ['correlation_score'], unique=False)
    op.create_index('ix_correlation_groups_environment', 'correlation_groups', ['environment'], unique=False)
    op.create_index('ix_correlation_groups_group_key', 'correlation_groups', ['group_key'], unique=False)
    op.create_index('ix_correlation_groups_incident_key', 'correlation_groups', ['incident_key'], unique=False)
    op.create_index('ix_correlation_groups_primary_service', 'correlation_groups', ['primary_service'], unique=False)
    op.create_index('ix_correlation_groups_status', 'correlation_groups', ['status'], unique=False)

    # 6. correlation_signals
    op.create_table(
        'correlation_signals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('signal_id', sa.String(length=255), nullable=False),
        sa.Column('signal_type', sa.String(length=64), nullable=False),
        sa.Column('service', sa.String(length=128), nullable=False),
        sa.Column('environment', sa.String(length=64), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False),
        sa.Column('source_reference', sa.String(length=255), nullable=True),
        sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('relationship_score', sa.Float(), nullable=False),
        sa.Column('relationship_reasons', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['correlation_groups.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'signal_id', name='uq_correlation_signals_group_signal')
    )
    op.create_index('ix_correlation_signals_group_id', 'correlation_signals', ['group_id'], unique=False)
    op.create_index('ix_correlation_signals_service', 'correlation_signals', ['service'], unique=False)
    op.create_index('ix_correlation_signals_signal_id', 'correlation_signals', ['signal_id'], unique=False)
    op.create_index('ix_correlation_signals_signal_type', 'correlation_signals', ['signal_type'], unique=False)
    op.create_index('ix_correlation_signals_timestamp', 'correlation_signals', ['timestamp'], unique=False)

    # 7. incidents
    op.create_table(
        'incidents',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('incident_key', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='DETECTED', nullable=False),
        sa.Column('environment', sa.String(length=64), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False, server_default='1.0'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_key')
    )
    op.create_index('ix_incidents_environment', 'incidents', ['environment'], unique=False)
    op.create_index('ix_incidents_incident_key', 'incidents', ['incident_key'], unique=False)
    op.create_index('ix_incidents_severity', 'incidents', ['severity'], unique=False)
    op.create_index('ix_incidents_status', 'incidents', ['status'], unique=False)

    # 8. incident_events
    op.create_table(
        'incident_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('incident_id', sa.UUID(), nullable=False),
        sa.Column('event_id', sa.String(length=255), nullable=False),
        sa.Column('relation_type', sa.String(length=64), nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['incident_id'], ['incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id', 'event_id', name='uq_incident_events_incident_event')
    )
    op.create_index('ix_incident_events_event_id', 'incident_events', ['event_id'], unique=False)
    op.create_index('ix_incident_events_incident_id', 'incident_events', ['incident_id'], unique=False)
    op.create_index('ix_incident_events_relation_type', 'incident_events', ['relation_type'], unique=False)

    # 9. processed_logs
    op.create_table(
        'processed_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('source_event_id', sa.String(length=255), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('service', sa.String(length=128), nullable=False),
        sa.Column('environment', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('raw_message', sa.Text(), nullable=False),
        sa.Column('normalized_message', sa.Text(), nullable=False),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('trace_id', sa.String(length=255), nullable=True),
        sa.Column('metadata_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_event_id')
    )
    op.create_index('ix_processed_logs_category', 'processed_logs', ['category'], unique=False)
    op.create_index('ix_processed_logs_environment', 'processed_logs', ['environment'], unique=False)
    op.create_index('ix_processed_logs_service', 'processed_logs', ['service'], unique=False)
    op.create_index('ix_processed_logs_severity', 'processed_logs', ['severity'], unique=False)
    op.create_index('ix_processed_logs_source_event_id', 'processed_logs', ['source_event_id'], unique=False)
    op.create_index('ix_processed_logs_timestamp', 'processed_logs', ['timestamp'], unique=False)
    op.create_index('ix_processed_logs_trace_id', 'processed_logs', ['trace_id'], unique=False)

    # 10. log_embeddings
    if conn.dialect.name == "postgresql":
        embedding_col = sa.Column('embedding', pgvector.sqlalchemy.Vector(dim=384), nullable=False)
    else:
        embedding_col = sa.Column('embedding', sa.JSON(), nullable=False)

    op.create_table(
        'log_embeddings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('log_id', sa.UUID(), nullable=False),
        sa.Column('model_name', sa.String(length=255), nullable=False),
        sa.Column('model_version', sa.String(length=64), nullable=True, server_default='1.0'),
        sa.Column('dimension', sa.Integer(), nullable=False),
        embedding_col,
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['log_id'], ['processed_logs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('log_id', 'model_name', 'model_version', name='uq_log_embeddings_log_model_version')
    )
    op.create_index('ix_log_embeddings_log_id', 'log_embeddings', ['log_id'], unique=False)

    # 11. rca_analyses
    op.create_table(
        'rca_analyses',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('analysis_key', sa.String(length=64), nullable=False),
        sa.Column('group_key', sa.String(length=64), nullable=False),
        sa.Column('analysis_version', sa.String(length=32), server_default='1.0', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('primary_root_cause', sa.String(length=255), nullable=False),
        sa.Column('primary_confidence', sa.Float(), nullable=False),
        sa.Column('causal_chain', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('analysis_key'),
        sa.UniqueConstraint('group_key', 'analysis_version', name='uq_rca_analyses_group_version')
    )
    op.create_index('ix_rca_analyses_analysis_key', 'rca_analyses', ['analysis_key'], unique=False)
    op.create_index('ix_rca_analyses_group_key', 'rca_analyses', ['group_key'], unique=False)
    op.create_index('ix_rca_analyses_primary_confidence', 'rca_analyses', ['primary_confidence'], unique=False)
    op.create_index('ix_rca_analyses_status', 'rca_analyses', ['status'], unique=False)

    # 12. root_cause_candidates
    op.create_table(
        'root_cause_candidates',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('analysis_id', sa.UUID(), nullable=False),
        sa.Column('candidate_type', sa.String(length=64), nullable=False),
        sa.Column('candidate_name', sa.String(length=255), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('rank', sa.Integer(), nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('evidence', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['rca_analyses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_root_cause_candidates_analysis_id', 'root_cause_candidates', ['analysis_id'], unique=False)
    op.create_index('ix_root_cause_candidates_candidate_type', 'root_cause_candidates', ['candidate_type'], unique=False)
    op.create_index('ix_root_cause_candidates_score', 'root_cause_candidates', ['score'], unique=False)

    # 13. causal_edges
    op.create_table(
        'causal_edges',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('analysis_id', sa.UUID(), nullable=False),
        sa.Column('source_signal_id', sa.String(length=255), nullable=False),
        sa.Column('target_signal_id', sa.String(length=255), nullable=False),
        sa.Column('relationship', sa.String(length=64), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('evidence', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_id'], ['rca_analyses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_causal_edges_analysis_id', 'causal_edges', ['analysis_id'], unique=False)
    op.create_index('ix_causal_edges_source_signal_id', 'causal_edges', ['source_signal_id'], unique=False)
    op.create_index('ix_causal_edges_target_signal_id', 'causal_edges', ['target_signal_id'], unique=False)

    # 14. runbooks
    op.create_table(
        'runbooks',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('runbook_key', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('service', sa.String(length=128), nullable=True),
        sa.Column('environment', sa.String(length=64), nullable=True),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('tags', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('runbook_key')
    )
    op.create_index('ix_runbooks_category', 'runbooks', ['category'], unique=False)
    op.create_index('ix_runbooks_environment', 'runbooks', ['environment'], unique=False)
    op.create_index('ix_runbooks_runbook_key', 'runbooks', ['runbook_key'], unique=False)
    op.create_index('ix_runbooks_service', 'runbooks', ['service'], unique=False)

    # 15. incident_summaries
    op.create_table(
        'incident_summaries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('summary_key', sa.String(length=64), nullable=False),
        sa.Column('incident_key', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('summary_version', sa.String(length=32), server_default='1.0', nullable=False),
        sa.Column('model_provider', sa.String(length=64), nullable=False),
        sa.Column('model_name', sa.String(length=255), nullable=False),
        sa.Column('executive_summary', sa.Text(), nullable=True),
        sa.Column('what_happened', sa.Text(), nullable=True),
        sa.Column('probable_root_cause', sa.Text(), nullable=True),
        sa.Column('impact_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), server_default='{}', nullable=False),
        sa.Column('timeline_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), server_default='[]', nullable=False),
        sa.Column('evidence_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), server_default='[]', nullable=False),
        sa.Column('remediation_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), server_default='[]', nullable=False),
        sa.Column('confidence', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('limitations_json', sa.JSON().with_variant(postgresql.JSONB(), 'postgresql'), server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('summary_key')
    )
    op.create_index('ix_incident_summaries_confidence', 'incident_summaries', ['confidence'], unique=False)
    op.create_index('ix_incident_summaries_incident_key', 'incident_summaries', ['incident_key'], unique=False)
    op.create_index('ix_incident_summaries_status', 'incident_summaries', ['status'], unique=False)
    op.create_index('ix_incident_summaries_summary_key', 'incident_summaries', ['summary_key'], unique=False)
    op.create_index('ix_incident_summaries_summary_version', 'incident_summaries', ['summary_version'], unique=False)


def downgrade() -> None:
    op.drop_table('incident_summaries')
    op.drop_table('runbooks')
    op.drop_table('causal_edges')
    op.drop_table('root_cause_candidates')
    op.drop_table('rca_analyses')
    op.drop_table('log_embeddings')
    op.drop_table('processed_logs')
    op.drop_table('incident_events')
    op.drop_table('incidents')
    op.drop_table('correlation_signals')
    op.drop_table('correlation_groups')
    op.drop_table('events')
    op.drop_table('anomaly_results')
    op.drop_table('metric_observations')
