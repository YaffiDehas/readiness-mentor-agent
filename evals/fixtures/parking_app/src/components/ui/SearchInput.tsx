import { TextField } from "@mui/material";
// Shared search box for list screens (MUI TextField with the project's spacing).
export function SearchInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return <TextField size="small" label={label} value={value} onChange={(e) => onChange(e.target.value)} />;
}
