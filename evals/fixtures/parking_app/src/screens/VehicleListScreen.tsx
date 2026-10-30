import { useState } from "react";
import { List } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { SearchInput } from "../components/ui/SearchInput";
import { ListRow } from "../components/ui/ListRow";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { fetchVehicles } from "../services/vehicles";

// Existing list screen with search: search text -> debounced -> React Query -> ListRow per item.
export function VehicleListScreen() {
  const [q, setQ] = useState("");
  const debounced = useDebouncedValue(q);
  const { data = [] } = useQuery({ queryKey: ["vehicles", debounced], queryFn: () => fetchVehicles(debounced) });
  return (
    <>
      <SearchInput label="Search vehicles" value={q} onChange={setQ} />
      <List>{data.map((v) => <ListRow key={v.id} primary={v.plate} secondary={v.enteredAt} />)}</List>
    </>
  );
}
