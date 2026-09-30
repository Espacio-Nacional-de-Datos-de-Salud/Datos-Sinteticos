// Shared placeholder used by every pipeline step that isn't implemented yet.
// Keeps the wizard navigation working end-to-end without duplicating boilerplate.

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function ComingSoon({ title, blurb }: { title: string; blurb: string }) {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Próximamente</CardTitle>
          <CardDescription>{blurb}</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Esta etapa aún no está implementada en el frontend. La funcionalidad
          del backend ya existe; se conectará en una iteración posterior.
        </CardContent>
      </Card>
    </div>
  );
}
