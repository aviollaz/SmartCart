import { ProductCard } from "./ProductCard";

export function ProductGrid({ products, emptyMessage }) {
  if (products.length === 0) {
    return <p className="py-12 text-center text-sm text-ink-muted">{emptyMessage}</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {products.map((product) => (
        <ProductCard key={product.unified_id} product={product} />
      ))}
    </div>
  );
}
