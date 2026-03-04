import { useState } from "react";
import type { Brief, Platform } from "../types";

interface BriefFormProps {
  loading: boolean;
  onSubmit: (brief: Brief) => void;
}

const DEFAULTS: Brief = {
  brand_name: "",
  product: "",
  target_audience: "",
  tone: "",
  platform: "youtube",
  duration_seconds: 30,
};

/** Form shown during INTAKE phase to collect the creative brief. */
export function BriefForm({ loading, onSubmit }: BriefFormProps) {
  const [form, setForm] = useState<Brief>(DEFAULTS);

  function set<K extends keyof Brief>(key: K, value: Brief[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit(form);
  }

  const isValid =
    form.brand_name.trim() &&
    form.product.trim() &&
    form.target_audience.trim() &&
    form.tone.trim();

  return (
    <div>
      <p className="section-title">Creative Brief</p>
      <div className="card">
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="brand_name">Brand Name</label>
            <input
              id="brand_name"
              type="text"
              value={form.brand_name}
              onChange={(e) => set("brand_name", e.target.value)}
              placeholder="e.g. Acme Corp"
              maxLength={120}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="product">Product / Service</label>
            <input
              id="product"
              type="text"
              value={form.product}
              onChange={(e) => set("product", e.target.value)}
              placeholder="e.g. Super Widget 3000"
              maxLength={200}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="target_audience">Target Audience</label>
            <input
              id="target_audience"
              type="text"
              value={form.target_audience}
              onChange={(e) => set("target_audience", e.target.value)}
              placeholder="e.g. Tech-savvy millennials"
              maxLength={300}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="tone">Tone</label>
            <input
              id="tone"
              type="text"
              value={form.tone}
              onChange={(e) => set("tone", e.target.value)}
              placeholder="e.g. fun and energetic"
              maxLength={200}
              required
            />
          </div>

          <div className="form-group">
            <label htmlFor="platform">Platform</label>
            <select
              id="platform"
              value={form.platform}
              onChange={(e) => set("platform", e.target.value as Platform)}
            >
              <option value="youtube">YouTube</option>
              <option value="tv">TV</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="duration">
              Duration: <strong>{form.duration_seconds}s</strong>
            </label>
            <input
              id="duration"
              type="range"
              min={5}
              max={120}
              step={5}
              value={form.duration_seconds}
              onChange={(e) =>
                set("duration_seconds", parseInt(e.target.value, 10))
              }
              style={{ padding: 0, border: "none", background: "transparent" }}
            />
          </div>

          <button
            type="submit"
            className="btn-primary"
            style={{ width: "100%" }}
            disabled={loading || !isValid}
          >
            {loading ? "Submitting…" : "Start Planning →"}
          </button>
        </form>
      </div>
    </div>
  );
}
