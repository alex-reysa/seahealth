"""Read-only smoke test: confirms PAT + host reach the workspace."""

from databricks_client import get_workspace


def main() -> None:
    w = get_workspace()
    me = w.current_user.me()
    print(f"Authenticated as: {me.user_name}  (id={me.id})")

    clusters = list(w.clusters.list())
    print(f"Clusters visible: {len(clusters)}")
    for c in clusters[:5]:
        print(f"  - {c.cluster_name}  state={c.state}  id={c.cluster_id}")

    warehouses = list(w.warehouses.list())
    print(f"SQL warehouses visible: {len(warehouses)}")
    for wh in warehouses[:5]:
        print(f"  - {wh.name}  state={wh.state}  id={wh.id}")


if __name__ == "__main__":
    main()
