"use client";

import { useRef, useState } from "react";
import { ImagePlus, Plus, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

const CURRENCIES = ["USD", "EUR", "GBP", "MAD"];

export function AddProductDialog({ onAdded }: { onAdded: () => void }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [sku, setSku] = useState("");
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setName("");
    setPrice("");
    setCurrency("USD");
    setSku("");
    setBrand("");
    setCategory("");
    setDescription("");
    setError(null);
    setImageFile(null);
    setImagePreview(null);
    setImageUrl(null);
    setGenerateError(null);
  }

  function handleImageSelect(file: File) {
    setImageFile(file);
    setImageUrl(null);
    setGenerateError(null);
    setImagePreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(file);
    });
  }

  async function handleGenerate() {
    if (!imageFile) return;
    setGenerateError(null);
    setGenerating(true);
    try {
      const result = await api.products.aiDescribe(imageFile);
      setName(result.title);
      setDescription(result.description);
      if (result.category) setCategory(result.category);
      setImageUrl(result.image_url);
    } catch (err) {
      setGenerateError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !price) {
      setError("Name and price are required.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await api.products.create({
        name: name.trim(),
        price: parseFloat(price),
        currency,
        image_url: imageUrl,
        description: description.trim() || null,
        sku: sku.trim() || null,
        brand: brand.trim() || null,
        category: category.trim() || null,
      });
      onAdded();
      setOpen(false);
      reset();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger
        render={
          <Button>
            <Plus className="size-4" />
            Add product
          </Button>
        }
      />
      <DialogContent>
        <DialogTitle>Add a product</DialogTitle>
        <DialogDescription>Name and price are the only required fields.</DialogDescription>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => imageInputRef.current?.click()}
              className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-md border border-dashed border-border bg-paper text-slate-soft transition-colors hover:border-slate-soft"
            >
              {imagePreview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={imagePreview} alt="" className="size-full object-cover" />
              ) : (
                <ImagePlus className="size-5" />
              )}
            </button>
            <input
              ref={imageInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleImageSelect(file);
              }}
            />
            <div className="flex-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={!imageFile || generating}
                onClick={handleGenerate}
              >
                <Sparkles className="size-3.5" />
                {generating ? "Generating…" : "Generate with AI"}
              </Button>
              <p className="mt-1 text-xs text-slate-soft">
                {imageFile
                  ? "Suggests a title, category, and factual description from the photo."
                  : "Add a photo to enable AI suggestions."}
              </p>
            </div>
          </div>
          {generateError && <p className="text-sm text-danger">{generateError}</p>}

          <div className="space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ceramic Vase" />
          </div>

          <div className="grid grid-cols-[1fr_auto] gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="price">Price</Label>
              <Input
                id="price"
                type="number"
                step="0.01"
                min="0"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="29.99"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="currency">Currency</Label>
              <select
                id="currency"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
                className="h-10 rounded-md border border-border bg-paper-raised px-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20"
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="description">Description (optional)</Label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full rounded-md border border-border bg-paper-raised px-3 py-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="brand">Brand (optional)</Label>
              <Input id="brand" value={brand} onChange={(e) => setBrand(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="category">Category (optional)</Label>
              <Input id="category" value={category} onChange={(e) => setCategory(e.target.value)} />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="sku">SKU (optional)</Label>
            <Input id="sku" value={sku} onChange={(e) => setSku(e.target.value)} />
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <Button type="submit" disabled={loading} className="w-full">
            {loading ? "Adding…" : "Add product"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
