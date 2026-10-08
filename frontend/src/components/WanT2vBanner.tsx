import { useQuery } from "@tanstack/react-query";
import { Alert } from "@mui/material";
import { api } from "../api/client";

type WanT2vStatus = {
  enabled: boolean;
  backend: string;
  mock: boolean;
  real_ai?: boolean;
  ready: boolean;
  load_state?: "idle" | "loading" | "loaded";
  loaded?: boolean;
  error?: string | null;
  hint?: string | null;
};

export default function WanT2vBanner() {
  const { data } = useQuery({
    queryKey: ["wan-t2v-status"],
    queryFn: async () => (await api.get("/video/wan-t2v/status")).data as WanT2vStatus,
    refetchInterval: (query) => (query.state.data?.load_state === "loading" ? 2000 : 5000),
  });
  if (!data) return null;
  if (data.real_ai && data.load_state === "loaded") {
    return (
      <Alert severity="success" variant="outlined">
        Wan2.1 T2V 1.3B is loaded. You can generate videos.
      </Alert>
    );
  }
  if (data.real_ai && data.load_state === "loading") {
    return (
      <Alert severity="info" variant="outlined">
        Wan2.1 T2V 1.3B is loading. Wait until this says you can generate videos.
      </Alert>
    );
  }
  if (data.real_ai) {
    return (
      <Alert severity="info" variant="outlined">
        Wan2.1 T2V 1.3B is installed via <strong>{data.backend}</strong>. It loads on the first
        clip, then this note changes to say you can generate videos.
      </Alert>
    );
  }
  if (data.mock) {
    return (
      <Alert severity="warning" variant="outlined">
        <strong>Mock mode</strong> — this is a solid-color stand-in, not Wan2.1. Set{" "}
        <code>WAN_T2V_MOCK=false</code> and install the local 1.3B weights.
      </Alert>
    );
  }
  return (
    <Alert severity="error" variant="outlined">
      Wan2.1 T2V 1.3B is not ready. {data.error || data.hint || "Install the local model."} This
      path does not use ComfyUI.
    </Alert>
  );
}
