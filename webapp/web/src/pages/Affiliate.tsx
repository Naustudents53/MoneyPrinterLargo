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
        title="Affiliate Marketing"
        description="Productos de Amazon vinculados a una cuenta Twitter."
      />
      <PageShell>
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
              <ul className="divide-y divide-border/60 rounded-lg border border-border/60">
                {products.map((p) => (
                  <li key={p.id} className="px-4 py-3 flex items-center gap-3">
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
