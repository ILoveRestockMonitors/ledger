import { existsSync, writeFileSync } from 'node:fs';
const D = [
  ['Main',        '01 · Plain',       0,    0,    1440, 1100],
  ['Receipt',     '02 · Receipt',     1560, 0,    1440, 1310],
  ['Ruled',       '03 · Ruled',       3120, 0,    1440, 1200],
  ['Swiss',       '04 · Swiss',       4680, 0,    1440, 1250],
  ['Calm',        '05 · Calm',        6240, 0,    1440, 1480],
  ['Almanac',     '06 · Almanac',     0,    1660, 1440, 1500],
  ['Terminal',    '07 · Terminal',    1560, 1660, 1440, 1350],
  ['Horizon',     '08 · Horizon',     3120, 1660, 1440, 1700],
  ['Atelier',     '09 · Atelier',     4680, 1660, 1440, 2010],
  ['Cartography', '10 · Cartography', 6240, 1660, 1440, 1620],
];
const present = D.filter(([stem]) => existsSync(`${stem}.dc.html`));
const canvas = {
  artboards: present.map(([stem, title, x, y, w, h]) => ({ file: `${stem}.dc.html`, title, x, y, w, h })),
  annotations: [{
    id: 'the-range', x: 0, y: -230, w: 760,
    text: 'Ten home-page directions for Ledger — ordered left to right, top to bottom.\n01 is the most reduced thing that still works. 10 is the most elaborate.\nEvery one shows the same September 2026 data, so they compare directly.',
  }],
  launch: { view: 'canvas' },
};
writeFileSync('canvas.json', JSON.stringify(canvas, null, 2) + '\n');
console.log(present.map(([s]) => `--artboard ${s}.dc.html`).join(' '));
