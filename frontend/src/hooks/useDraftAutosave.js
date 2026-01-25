import { useEffect } from "react";
import debounce from "lodash.debounce";

export default function useDraftAutosave(draft) {
  useEffect(() => {
    if (!draft?.id) return;

    const save = debounce(() => {
      fetch(`/api/drafts/${draft.id}/update/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          blue_team: draft.blue_team,
          red_team: draft.red_team,
          picks: draft.picks,
          bans: draft.bans,
          status: draft.status,
        }),
      });
    }, 400);

    save();

    return () => save.cancel();
  }, [draft]);
}
