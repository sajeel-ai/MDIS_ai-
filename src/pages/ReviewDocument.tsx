import { AppLayout } from "../layouts/AppLayout"
import { ReviewCenter as ReviewCenterView } from "../views/ReviewCenter"
import { ReviewWorkspace } from "../components/review/ReviewWorkspace"
import { isReviewWorkspaceEnabled } from "../config/featureFlags"

export interface ReviewDocumentPageProps {
  onNavigate: (view: string, documentId?: string, reviewTaskId?: string, fromStatus?: string | null) => void
  reviewTaskId?: string | null
  fromStatus?: string | null
}

/** Full-screen review workspace for one document. */
export function ReviewDocumentPage({ onNavigate, reviewTaskId, fromStatus }: ReviewDocumentPageProps) {
  return (
    <AppLayout activeView="review" onNavigate={onNavigate}>
      {isReviewWorkspaceEnabled()
        ? <ReviewWorkspace initialTaskId={reviewTaskId} />
        : <ReviewCenterView
            onNavigate={onNavigate}
            initialTaskId={reviewTaskId}
            fromStatus={fromStatus}
            detailOnly
          />}
    </AppLayout>
  )
}
