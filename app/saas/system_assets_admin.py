"""Explicit, auditable promotion of tenant media into the platform catalog."""

from __future__ import annotations

import argparse

from sqlalchemy import select

from .database import SessionLocal
from .models import Asset, Avatar
from .system_assets import publish_template


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote approved assets into the platform catalog")
    parser.add_argument("--source-tenant", required=True, help="Exact workspace ID owning the source media")
    parser.add_argument("--avatars", required=True, help="Comma-separated avatar names to promote")
    parser.add_argument("--all-backgrounds", action="store_true", help="Promote each unique background SHA-256 once")
    parser.add_argument("--confirm-platform-license", action="store_true", help="Confirm these media may be used by all tenants")
    args = parser.parse_args()
    if not args.confirm_platform_license:
        parser.error("Publishing requires --confirm-platform-license")
    names = {value.strip() for value in args.avatars.split(",") if value.strip()}
    if not names:
        parser.error("At least one avatar name is required")

    with SessionLocal() as db:
        avatars = db.scalars(select(Avatar).where(Avatar.tenant_id == args.source_tenant)).all()
        matches = [avatar for avatar in avatars if avatar.name in names]
        if {avatar.name for avatar in matches} != names or len(matches) != len(names):
            parser.error("Avatar selection must match unique names in the specified workspace")
        backgrounds = []
        if args.all_backgrounds:
            rows = db.scalars(select(Asset).where(Asset.tenant_id == args.source_tenant,
                                                 Asset.kind == "background").order_by(Asset.created_at)).all()
            seen: set[str] = set()
            for asset in rows:
                digest = asset.sha256 or asset.id
                if digest not in seen:
                    backgrounds.append(asset)
                    seen.add(digest)
        for avatar in matches:
            item = publish_template(db, kind="avatar", source_id=avatar.id)
            print(f"avatar: {item.name} ({item.id})")
        for background in backgrounds:
            item = publish_template(db, kind="background", source_id=background.id)
            print(f"background: {item.name} ({item.id})")
        print(f"Published {len(matches)} avatars and {len(backgrounds)} unique backgrounds")


if __name__ == "__main__":
    main()
