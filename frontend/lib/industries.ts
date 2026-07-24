// Common industry/market categories for the onboarding selector. "Other"
// is always appended by the UI, not stored here, so the free-text fallback
// stays a UI concern rather than a magic string baked into the data.
export const INDUSTRIES = [
  "Electronics & Tech Gadgets",
  "Fashion & Apparel",
  "Beauty & Personal Care",
  "Home & Garden",
  "Food & Beverage",
  "Health & Wellness",
  "Sporting Goods & Outdoors",
  "Toys & Kids",
  "Automotive & Parts",
  "Furniture & Home Decor",
  "Jewelry & Accessories",
  "Pet Supplies",
  "Office & Industrial Supplies",
  "Books & Media",
] as const;
