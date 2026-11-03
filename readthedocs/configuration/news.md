# News file: `streamhub-news.json`

A JSON array of announcements, newest first. The home page shows the first three; the **News** page shows all of them.

```json
[
  { "title": "Sales forecast v2", "date": "2026-11-02", "type": "info",
    "message": "The forecast now covers every region and refreshes each Monday." },
  { "title": "Maintenance on Saturday", "date": "2026-10-30", "type": "warning",
    "message": "The hub restarts at 06:00. Save your work before then." }
]
```

| Key | Description |
|---|---|
| `title` | Required: entries without a title are skipped |
| `date` | Free text, shown as is |
| `message` | The text of the announcement |
| `type` | `normal`, `info` (blue) or `warning` (orange) |

Edit it on the admin page's [News](../admin-guide/news.md) tab, or on disk: changes apply on the next request.
