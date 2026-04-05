from django.contrib import admin
from .models import AuditBatch, TimestampProof, MatrixRoomReference, PGPKeyPublication, ProofExport


@admin.register(AuditBatch)
class AuditBatchAdmin(admin.ModelAdmin):
    list_display = ['git_commit_hash_short', 'event_count', 'stamped_at', 'verified_at', 'bitcoin_block']
    list_filter = ['verified_at', 'stamped_at']
    search_fields = ['git_commit_hash']
    readonly_fields = ['git_commit_hash', 'git_commit_file', 'ots_proof', 'stamped_at',
                       'verified_at', 'bitcoin_block', 'event_count']

    @admin.display(description='Git Commit')
    def git_commit_hash_short(self, obj):
        return obj.git_commit_hash[:8] if obj.git_commit_hash else '—'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(TimestampProof)
class TimestampProofAdmin(admin.ModelAdmin):
    list_display = ('object_id', 'content_type', 'data_hash', 'created_at', 'verified_at', 'bitcoin_block')
    list_filter = ('content_type', 'verified_at')
    search_fields = ('object_id', 'data_hash')
    readonly_fields = ('data_hash', 'ots_proof', 'created_at', 'verified_at', 'bitcoin_block')


@admin.register(MatrixRoomReference)
class MatrixRoomReferenceAdmin(admin.ModelAdmin):
    list_display = ('object_id', 'content_type', 'room_id', 'purpose', 'is_encrypted', 'created_at')
    list_filter = ('purpose', 'is_encrypted')
    search_fields = ('object_id', 'room_id')
    readonly_fields = ('room_id', 'event_id', 'created_at')


@admin.register(PGPKeyPublication)
class PGPKeyPublicationAdmin(admin.ModelAdmin):
    list_display = ('profile', 'fingerprint', 'published_at', 'revoked', 'git_commit_hash')
    list_filter = ('revoked', 'published_at')
    search_fields = ('profile__id', 'fingerprint')
    readonly_fields = ('fingerprint', 'public_key', 'published_at', 'git_commit_hash')


@admin.register(ProofExport)
class ProofExportAdmin(admin.ModelAdmin):
    list_display = ('profile', 'export_type', 'created_at', 'file_hash')
    list_filter = ('export_type', 'created_at')
    search_fields = ('profile__id', 'file_hash')
    readonly_fields = ('created_at', 'file_hash', 'object_ids')
