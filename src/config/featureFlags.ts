/** Review workspace stays disabled until explicitly enabled by the deployment. */
export function isReviewWorkspaceEnabled(): boolean {
  if (typeof window !== 'undefined' && (window as Window & { __ENABLE_REVIEW_WORKSPACE__?: boolean }).__ENABLE_REVIEW_WORKSPACE__ === true) {
    return true
  }
  return import.meta.env.VITE_ENABLE_REVIEW_WORKSPACE === 'true'
}
