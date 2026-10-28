const DEFAULT_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
const configuredLimit = Number(import.meta.env.VITE_MAX_UPLOAD_SIZE_BYTES)
export const MAX_UPLOAD_BYTES = Number.isFinite(configuredLimit) && configuredLimit > 0
  ? configuredLimit
  : DEFAULT_MAX_UPLOAD_BYTES

const SIGNATURES: Record<string, (header: Uint8Array) => boolean> = {
  '.pdf': (header) => header[0] === 0x25 && header[1] === 0x50 && header[2] === 0x44 && header[3] === 0x46 && header[4] === 0x2d,
  '.png': (header) => [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a].every((byte, index) => header[index] === byte),
  '.jpg': (header) => header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff,
  '.jpeg': (header) => header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff,
  '.tiff': (header) => (header[0] === 0x49 && header[1] === 0x49 && header[2] === 0x2a && header[3] === 0x00)
    || (header[0] === 0x4d && header[1] === 0x4d && header[2] === 0x00 && header[3] === 0x2a),
}

export async function validateUploadFile(file: File, maxBytes = MAX_UPLOAD_BYTES): Promise<string | null> {
  const extension = file.name.toLowerCase().match(/\.[^.]+$/)?.[0] || ''
  if (!SIGNATURES[extension] && extension !== '.txt') {
    return 'Unsupported file type. Choose a PDF, PNG, JPG, TIFF, or TXT file.'
  }
  if (file.size > maxBytes) {
    return `File exceeds the configured upload size limit of ${Math.floor(maxBytes / (1024 * 1024))} MiB.`
  }
  if (file.size === 0) return 'The selected file is empty.'

  const bytes = new Uint8Array(await file.slice(0, 16).arrayBuffer())
  if (extension === '.txt') {
    const hasUtf16Bom = bytes[0] === 0xff && bytes[1] === 0xfe
      || bytes[0] === 0xfe && bytes[1] === 0xff
    if (bytes.includes(0) && !hasUtf16Bom) return 'TXT files containing null bytes are not supported.'
    return null
  }
  if (!SIGNATURES[extension](bytes)) {
    return 'File contents do not match the selected file type. The file may be corrupt.'
  }
  return null
}
