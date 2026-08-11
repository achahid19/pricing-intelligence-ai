"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

const CONFIRM_WORD = "DELETE";

export function DeleteAllProductsDialog({ count, onDeleted }: { count: number; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      setConfirmText("");
      setError(null);
    }
  }

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await api.products.deleteAll();
      setOpen(false);
      setConfirmText("");
      onDeleted();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <button
            type="button"
            className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium text-danger/70 transition-colors hover:bg-danger/10 hover:text-danger"
          >
            <Trash2 className="size-3.5" />
            Delete all
          </button>
        }
      />
      <DialogContent>
        <DialogTitle>Delete all products</DialogTitle>
        <DialogDescription>
          {`This permanently deletes all ${count} product${count === 1 ? "" : "s"} in your catalog, along with their price history and any confirmed competitor matches. This can't be undone.`}
        </DialogDescription>

        <div className="mt-4 space-y-3">
          <div>
            <label className="text-xs font-medium text-slate">
              Type <span className="font-[family-name:var(--font-data)] font-semibold text-danger">{CONFIRM_WORD}</span>{" "}
              to confirm
            </label>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={CONFIRM_WORD}
              className="mt-1.5"
              autoFocus
            />
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <Button
            type="button"
            onClick={handleDelete}
            disabled={confirmText !== CONFIRM_WORD || deleting}
            className="w-full bg-danger text-white hover:bg-danger/90"
          >
            {deleting ? "Deleting…" : `Delete ${count} product${count === 1 ? "" : "s"}`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
