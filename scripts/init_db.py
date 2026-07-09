from cricket_edge.database import Database
from cricket_edge.seed import seed_demo_data


def main() -> None:
    db = Database()
    db.init_schema()
    seed_demo_data(db)
    print(f"Initialized {db.path}")


if __name__ == "__main__":
    main()
