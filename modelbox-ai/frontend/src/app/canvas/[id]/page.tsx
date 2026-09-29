'use client';

/**
 * /canvas/<id> — a saved model, reopened from the server (Sprint 8 Step 3).
 *
 * The canvas used to hold its model id only in memory, so a reload, a new tab
 * or a shared link showed an empty canvas. Here the id is in the URL and the
 * model is read from the server on arrival, so it reopens exactly as it was
 * saved. The one exception is deliberate: if this same model is already on
 * the canvas with unsaved changes, they are kept rather than overwritten.
 */

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';

import CanvasPage from '@/app/canvas/page';
import { ErrorState, LoadingState } from '@/components/ui';
import { getModel } from '@/lib/api';
import { errMessage } from '@/lib/errors';
import { useCanvasStore } from '@/store/canvasStore';

export default function CanvasByIdPage() {
  const { id } = useParams<{ id: string }>();
  const loadModel = useCanvasStore((s) => s.loadModel);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const { modelId, dirty } = useCanvasStore.getState();
    if (modelId === id && dirty) {
      setReady(true);
      return;
    }
    let live = true;
    setReady(false);
    getModel(id)
      .then((model) => {
        if (!live) return;
        loadModel(model);
        setReady(true);
      })
      .catch((e) => live && setError(errMessage(e, 'This model could not be opened.')));
    return () => {
      live = false;
    };
  }, [id, loadModel]);

  if (error) return <ErrorState title="Model unavailable">{error}</ErrorState>;
  if (!ready) return <LoadingState label="Opening the model…" />;
  return <CanvasPage />;
}
