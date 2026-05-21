import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import yaml from "js-yaml";
import { api, type ConfigContent } from "@/lib/api";
import { extractDetail } from "@/lib/errors";

export function useApplyModePreset() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async (preset: Record<string, unknown>) => {
      const configQuery = await api.get<ConfigContent>("/configs/mostly_ai");
      const currentContent = configQuery.data.content;
      const current = (yaml.load(currentContent) as Record<string, unknown>) ?? {};

      // Deep merge preset into current config
      const merged = deepMerge(current, preset);

      const newContent = yaml.dump(merged, { lineWidth: 100, noRefs: true });
      const { data } = await api.put<ConfigContent>("/configs/mostly_ai", {
        content: newContent,
      });
      return data;
    },
    onSuccess: () => {
      toast.success("Configuración actualizada");
      // Mark query as stale so it refetches when accessed
      queryClient.invalidateQueries({
        queryKey: ["config", "mostly_ai"],
        refetchType: "all"
      });
    },
    onError: (err) => {
      toast.error(`No se pudo aplicar el preset: ${extractDetail(err)}`);
    },
  });

  return mutation;
}

function deepMerge(
  target: Record<string, unknown>,
  source: Record<string, unknown>,
): Record<string, unknown> {
  const result = { ...target };

  for (const [key, value] of Object.entries(source)) {
    // If source value is null, remove the key from result
    if (value === null) {
      delete result[key];
    }
    // If source value is an object and target also has an object at this key, merge recursively
    else if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      key in target &&
      target[key] &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      result[key] = deepMerge(
        target[key] as Record<string, unknown>,
        value as Record<string, unknown>,
      );
    }
    // Otherwise, replace the value
    else {
      result[key] = value;
    }
  }

  return result;
}
