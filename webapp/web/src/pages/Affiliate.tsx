import { useEffect, useState } from "react";
import { ShoppingBag } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { PageShell } from "@/components/layout/AppShell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";

export function Affiliate() {
  const [products, setProducts] = useState<{ id: string; affiliate_link: string; twitter_uuid: string }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/products")
      .then((r) => r.json())
      .then(setProducts)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <Header
        eyebrow="Monetizacion"
        title="Affiliate Marketing"
        description="Productos de Amazon vinculados a una cuenta Twitter."
      />
      <PageShell>
        <section className="page-hero">
          <div className="page-hero-inner">
            <div>
              <span className="eyebrow block mb-2">Revenue shelf</span>
              <h1 className="page-title">
                Productos con <span className="brand-text">tracking</span>
              </h1>
              <p className="page-subtitle">
                Links afiliados conectados a cuentas sociales para mantener el
                inventario comercial visible.
              </p>
            </div>
            <div className="metric-strip grid-cols-1 w-full sm:w-auto sm:min-w-[220px]">
              <div className="px-4 py-3">
                <span className="tiny-label">Productos</span>
                <div className="mt-1 font-mono text-[17px] font-semibold">{products.length}</div>
              </div>
            </div>
          </div>
        </section>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShoppingBag className="h-4 w-4 text-gold" /> Productos
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-12" />
                ))}
              </div>
            ) : products.length === 0 ? (
              <EmptyState
                icon={ShoppingBag}
                title="Sin productos"
                description="Agrega un producto desde el CLI o vía API. Esta sección listará productos vinculados a una cuenta Twitter."
              />
            ) : (
              <ul className="space-y-2">
                {products.map((p) => (
                  <li key={p.id} className="list-row rounded-xl px-4 py-3 flex items-center gap-3">
                    <Badge variant="gold" className="font-mono">
                      {p.id.slice(0, 8)}
                    </Badge>
                    <a
                      href={p.affiliate_link}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sm flex-1 truncate hover:underline"
                    >
                      {p.affiliate_link}
                    </a>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      tw: {p.twitter_uuid.slice(0, 8)}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </PageShell>
    </>
  );
}
