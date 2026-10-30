import { ListItem, ListItemText } from "@mui/material";
// One row of a list screen: primary text and a secondary line.
export function ListRow({ primary, secondary }: { primary: string; secondary?: string }) {
  return <ListItem divider><ListItemText primary={primary} secondary={secondary} /></ListItem>;
}
