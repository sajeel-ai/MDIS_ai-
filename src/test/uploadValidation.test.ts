import { describe, expect, it } from 'vitest'
import { validateUploadFile } from '../utils/uploadValidation'

function file(name: string, bytes: number[], size = bytes.length) {
  const upload = new File([new Uint8Array(bytes)], name, { type: 'application/octet-stream' })
  if (size !== bytes.length) Object.defineProperty(upload, 'size', { value: size })
  return upload
}

describe('upload signature and size validation', () => {
  it('accepts a PDF with a PDF signature', async () => {
    await expect(validateUploadFile(file('note.pdf', [0x25, 0x50, 0x44, 0x46, 0x2d]))).resolves.toBeNull()
  })

  it('accepts UTF-16 text with a byte-order mark', async () => {
    await expect(validateUploadFile(file('note.txt', [0xff, 0xfe, 0x61, 0x00]))).resolves.toBeNull()
  })

  it('rejects unsupported types, mismatched signatures, corrupt binary text, and oversized files', async () => {
    await expect(validateUploadFile(file('note.docx', [0x50, 0x4b, 0x03, 0x04]))).resolves.toMatch(/Unsupported/)
    await expect(validateUploadFile(file('note.pdf', [0x00, 0x01]))).resolves.toMatch(/contents do not match/i)
    await expect(validateUploadFile(file('note.txt', [0x61, 0x00, 0x62]))).resolves.toMatch(/null bytes/i)
    await expect(validateUploadFile(file('large.txt', [0x61], 25 * 1024 * 1024 + 1))).resolves.toMatch(/25 MiB/i)
  })
})
