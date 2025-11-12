# HAM Radio Design - Notes

## Design Decision

**Selected Style:** HAM Radio Vintage with Pixel Art

## Key Features

### Main Hero Character
- Large pixel art radio operator (80x80px)
- Radio backpack with LED display
- Antenna with pulsing signal
- Positioned in header next to logo

### Color Palette
- `#2c2416` - Dark brown (background)
- `#3d3020` - Medium brown (panels)
- `#8b7355` - Brown metal (borders)
- `#d4c5a0` - Beige (text)
- `#ff6b35` - Orange LED (accents)
- `#ffa500` - Yellow/gold (points)
- `#00ff00` - Green LED (active)
- `#1a1410` - Very dark brown (shadows)

### Layout
- **3-column layout:** Left panel | Center MAP | Right panel
- Map is the main focus (~60% width)
- Compact side panels for secondary info
- Responsive design

### Visual Style
- Vintage radio equipment aesthetic
- Physical details (screws, shadows, borders)
- Warm color palette
- Minimalist, clean design
- Pixel art characters and icons

### Characters
- **Players/Operators:** Pixel art characters with radio packs
- **Devices:** Simple antenna towers
- LED indicators in different colors

### Typography
- **Primary:** Share Tech Mono (clean, readable)
- **Display:** VT323 (pixel style for titles and numbers)

## Files

1. `design_preview.html` - Matrix style (alternative)
2. `design_preview_hamradio.html` - HAM radio initial
3. `design_preview_hamradio_final.html` - HAM radio with hero + map layout (FINAL)

## Next Steps

- [ ] Implement design to index.html
- [ ] Implement design to player.html
- [ ] Implement design to rules.html
- [ ] Implement design to winners.html
- [ ] Implement design to coverage.html
- [ ] Create reusable CSS components
- [ ] Add map integration with Leaflet
- [ ] Test on different screen sizes

## Notes

- Map should be the primary focus
- Keep side panels minimal and scrollable
- Hero character is the main branding element
- Use HAM radio terminology (QSL, operators, signals)
