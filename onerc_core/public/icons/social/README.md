# Social Media Icons

SVG icons referenced by the **Social Media Sites** doctype.

## Adding an icon

1. Download the SVG from [simpleicons.org](https://simpleicons.org) (MIT licensed, brand-accurate).
2. Save it here as `<name>.svg` using a lowercase, hyphenated filename (e.g. `twitter.svg`, `linkedin.svg`, `bluesky.svg`).
3. Run `bench build --app onerc_core`.
4. In the **Social Media Sites** doctype, set the `Social Media Icon` field to the filename without extension (e.g. `twitter`).

## Resolved asset path

Icons are served at:

```
/assets/onerc_core/icons/social/<name>.svg
```

## Naming convention

- All lowercase
- Hyphens for spaces (e.g. `youtube-music.svg`)
- Match the Simple Icons slug where possible
