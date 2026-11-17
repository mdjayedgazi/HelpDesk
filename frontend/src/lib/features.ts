/**
 * Feature switches baked into the frontend build.
 *
 * Attachments are disabled in the public college-demo deployment because that
 * profile does not run ClamAV. The backend is authoritative and rejects uploads
 * independently; this only hides controls the user cannot use.
 */
export function resolveAttachmentsEnabled(rawValue: string | undefined): boolean {
  return rawValue?.trim().toLowerCase() !== 'false'
}

export const attachmentsEnabled = resolveAttachmentsEnabled(
  import.meta.env.VITE_ATTACHMENTS_ENABLED,
)
