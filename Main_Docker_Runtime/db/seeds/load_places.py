"""
db/seeds/load_places.py
CSV → places + alias 테이블 벌크 로드.

사용법:
  docker exec TA_backend python db/seeds/load_places.py
"""
import csv
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

DB_URL = os.environ["DATABASE_URL"]

PLACES_CSV = Path(__file__).parent / "DB_Places_Master_Final.csv"
ALIAS_CSV  = Path(__file__).parent / "DB_Place_Aliases_Finalv.csv"

PLACES_INSERT = """
    INSERT INTO places (
        place_id, name, main_category, sub_category, address_road,
        lat, lon, region, region_depth_2,
        geom,
        place_type, created_at
    )
    VALUES %s
    ON CONFLICT (place_id) DO UPDATE SET
        name           = EXCLUDED.name,
        main_category  = EXCLUDED.main_category,
        sub_category   = EXCLUDED.sub_category,
        address_road   = EXCLUDED.address_road,
        lat            = EXCLUDED.lat,
        lon            = EXCLUDED.lon,
        region         = EXCLUDED.region,
        region_depth_2 = EXCLUDED.region_depth_2,
        geom           = EXCLUDED.geom
"""

ALIAS_INSERT = """
    INSERT INTO alias (alias_id, place_id, alias)
    VALUES %s
    ON CONFLICT (alias_id) DO NOTHING
"""


def _parse_float(val):
    try:
        return float(val) if val and val.strip() else None
    except ValueError:
        return None


def load_places(conn):
    rows = []
    with open(PLACES_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            lat = _parse_float(r.get("lat"))
            lon = _parse_float(r.get("lon"))
            geom = f"SRID=4326;POINT({lon} {lat})" if lat and lon else None
            rows.append((
                r["place_id"],
                r["name"],
                r.get("main_category") or None,
                r.get("sub_category") or None,
                r.get("address_road") or r.get("address_jibun") or None,
                lat, lon,
                r.get("region") or None,
                r.get("region_depth_2") or None,
                geom,
                r.get("main_category") or "기타",  # place_type
                "NOW()",  # created_at — handled by server_default
            ))

    # geom은 psycopg2가 WKT 문자열로 보내야 하므로 별도 처리
    with conn.cursor() as cur:
        batch = []
        for r in rows:
            *rest, geom, place_type, _ = r
            place_id, name, main_cat, sub_cat, addr, lat, lon, region, region_d2 = rest
            batch.append((
                place_id, name, main_cat, sub_cat, addr, lat, lon, region, region_d2,
                geom, place_type,
            ))

        execute_values(
            cur,
            """
            INSERT INTO places (
                place_id, name, main_category, sub_category, address_road,
                lat, lon, region, region_depth_2,
                geom, place_type
            )
            VALUES %s
            ON CONFLICT (place_id) DO UPDATE SET
                name           = EXCLUDED.name,
                main_category  = EXCLUDED.main_category,
                sub_category   = EXCLUDED.sub_category,
                address_road   = EXCLUDED.address_road,
                lat            = EXCLUDED.lat,
                lon            = EXCLUDED.lon,
                region         = EXCLUDED.region,
                region_depth_2 = EXCLUDED.region_depth_2,
                geom           = EXCLUDED.geom
            """,
            [
                (p, n, mc, sc, ad, la, lo, rg, rd,
                 f"SRID=4326;POINT({lo} {la})" if la and lo else None,
                 mc or "기타")
                for p, n, mc, sc, ad, la, lo, rg, rd, _, _ in batch
            ],
            template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,ST_GeomFromEWKT(%s),%s)",
            page_size=500,
        )
    print(f"[places] {len(batch)}건 upsert 완료")


def load_aliases(conn):
    rows = []
    with open(ALIAS_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append((r["alias_id"], r["place_id"], r["alias"]))

    with conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO alias (alias_id, place_id, alias) VALUES %s ON CONFLICT (alias_id) DO NOTHING",
            rows,
            page_size=1000,
        )
    print(f"[alias] {len(rows)}건 insert 완료")


def main():
    conn = psycopg2.connect(DB_URL)
    try:
        load_places(conn)
        load_aliases(conn)
        conn.commit()
        print("완료")
    except Exception as e:
        conn.rollback()
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
