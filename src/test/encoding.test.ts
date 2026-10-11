import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, resolve } from "node:path"
import { describe, expect, it } from "vitest"

const sourceRoot = resolve(process.cwd(), "src")
const textExtensions = new Set([
  ".ts",
  ".tsx",
  ".css",
  ".html",
  ".json",
  ".svg",
])

function sourceFiles(root: string): string[] {
  return readdirSync(root).flatMap((entry) => {
    const file = join(root, entry)
    if (statSync(file).isDirectory()) return sourceFiles(file)
    return textExtensions.has(file.slice(file.lastIndexOf("."))) ? [file] : []
  })
}

describe("source encoding", () => {
  it("contains no UTF-8 mojibake sequences", () => {
    const mojibakePrefix = String.fromCharCode(0xe2, 0xc2, 0xc3)
    const mojibake = new RegExp(`(?:[${mojibakePrefix}])[\\u0080-\\uFFFF]`)
    const offenders = sourceFiles(sourceRoot).filter((file) =>
      mojibake.test(readFileSync(file, "utf8")),
    )
    expect(offenders).toEqual([])
  })
})
