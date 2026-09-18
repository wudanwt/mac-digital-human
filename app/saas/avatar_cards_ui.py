from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
/* Digital human asset cards -------------------------------------------------
   Keep the asset page visually quiet: the portrait is the hero, operational
   metadata is compact, and secondary details do not push every card taller.
*/
#page > .grid:has([data-dh-image-id]) {
  grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
  gap: 18px !important;
  align-items: stretch;
}

#page > .grid > .card:has([data-dh-image-id]) {
  padding: 0 !important;
  overflow: hidden !important;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-color: rgba(151,176,214,.12);
  background: linear-gradient(180deg, rgba(18,24,33,.95), rgba(11,15,21,.96));
  box-shadow: 0 18px 46px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.015);
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}

#page > .grid > .card:has([data-dh-image-id]):hover {
  transform: translateY(-3px);
  border-color: rgba(113,183,255,.28);
  box-shadow: 0 24px 58px rgba(0,0,0,.32), 0 0 0 1px rgba(113,183,255,.04);
}

#page > .grid > .card > [data-dh-image-id] {
  height: auto !important;
  aspect-ratio: 16 / 10;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 12%, rgba(113,183,255,.14), transparent 44%),
    linear-gradient(145deg,#172237,#0b111a) !important;
  border-bottom: 1px solid rgba(151,176,214,.10);
}

#page > .grid > .card > [data-dh-image-id] img {
  width: 100% !important;
  height: 100% !important;
  object-fit: cover !important;
  object-position: center 18% !important;
  display: block;
  transition: transform .28s ease, filter .28s ease;
}

#page > .grid > .card:hover > [data-dh-image-id] img {
  transform: scale(1.018);
  filter: saturate(1.02) contrast(1.015);
}

#page > .grid > .card > [data-dh-image-id] + div {
  padding: 17px 17px 16px !important;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

#page > .grid > .card > [data-dh-image-id] + div > div:first-child {
  min-height: 47px;
  align-items: flex-start !important;
}

#page > .grid > .card:has([data-dh-image-id]) h3 {
  margin: 0 0 2px !important;
  font-size: 17px;
  line-height: 1.28;
  letter-spacing: 0;
  color: #f3f7ff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

#page > .grid > .card:has([data-dh-image-id]) h3 + .muted {
  font-size: 11px !important;
  line-height: 1.45;
  color: #6f7e92 !important;
}

#page > .grid > .card:has([data-dh-image-id]) .badge {
  flex: 0 0 auto;
  margin-top: 1px;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(2) {
  margin-top: 11px !important;
  padding: 10px 11px !important;
  border-color: rgba(151,176,214,.10) !important;
  border-radius: 10px !important;
  background: rgba(8,13,20,.62) !important;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(2) > div:first-child {
  font-size: 12px;
  font-weight: 680 !important;
  color: #dce7f5;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(2) > .muted {
  margin-top: 1px;
  font-size: 10px !important;
  color: #657286 !important;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(3):not(.actions) {
  margin-top: 9px !important;
  padding: 9px 10px !important;
  border-radius: 10px !important;
  background: rgba(9,17,25,.58) !important;
  border-color: rgba(113,183,255,.12) !important;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(3):not(.actions) > div:first-child {
  margin-bottom: 4px !important;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(3):not(.actions) > div:first-child b {
  font-size: 11px !important;
  color: #8ebee8 !important;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(3):not(.actions) > div:nth-child(2) {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  white-space: normal !important;
  line-height: 1.55 !important;
  min-height: 3.1em;
  max-height: 3.1em;
  font-size: 11px;
  color: #b9c7d9 !important;
}

#page > .grid > .card > [data-dh-image-id] + div > div:nth-child(3):not(.actions) > .muted:last-child {
  display: none;
}

#page > .grid > .card:has([data-dh-image-id]) .actions {
  margin-top: auto !important;
  padding-top: 13px;
  display: grid !important;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 7px !important;
  align-items: stretch;
}

#page > .grid > .card:has([data-dh-image-id]) .actions button {
  min-width: 0;
  min-height: 36px;
  padding: 8px 7px;
  border-radius: 9px;
  font-size: 11px;
  line-height: 1.25;
  white-space: normal;
}

#page > .grid > .card:has([data-dh-image-id]) [data-dh-preview-video] { grid-column: 1; grid-row: 1; }
#page > .grid > .card:has([data-dh-image-id]) [data-dh-preview-audio] { grid-column: 2; grid-row: 1; }
#page > .grid > .card:has([data-dh-image-id]) [data-dh-edit] { grid-column: 3; grid-row: 1; }
#page > .grid > .card:has([data-dh-image-id]) [data-dh-review-transcript] { grid-column: 1 / span 2; grid-row: 2; }
#page > .grid > .card:has([data-dh-image-id]) [data-dh-delete] { grid-column: 3; grid-row: 2; }

#page > .grid > .card:has([data-dh-image-id]) [data-dh-edit] {
  border-color: rgba(113,183,255,.20);
  color: #d9edff;
}

#page > .grid > .card:has([data-dh-image-id]) [data-dh-delete] {
  background: transparent;
  border-color: rgba(255,115,140,.12);
  color: #d78494;
}

@media (max-width: 1220px) {
  #page > .grid:has([data-dh-image-id]) {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }
}

@media (max-width: 760px) {
  #page > .grid:has([data-dh-image-id]) {
    grid-template-columns: 1fr !important;
  }
  #page > .grid > .card > [data-dh-image-id] {
    aspect-ratio: 16 / 9;
  }
}
'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")
