"""Walking the category tree.

`categories.parent_id` is the schema's only self-reference, and two very different
features need the same walk:

* the storefront, where clicking a parent category must show everything underneath
  it -- with the seeded tree, "apparel" holds no products directly and both its
  children do, so a non-recursive filter shows an empty catalogue;
* the admin portal, where re-parenting a category under one of its own descendants
  would create a detached cycle. **The foreign key cannot catch that**: every
  `parent_id` still points at a real row, so the constraint is satisfied while the
  branch floats free of every root, invisible to the storefront and impossible to
  fix through the UI that created it.

Framework-free like the rest of `services/`: it takes a Session, so a router, a
script and a test can all ask the same question the same way.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category


def descendant_ids(db: Session, category_id: int) -> list[int]:
    """`category_id` plus every category beneath it, at any depth.

    `WITH RECURSIVE` is the SQL tool for this. The first SELECT is the anchor --
    the category itself; the second repeatedly joins children onto what has been
    found so far, until nothing new appears. One query, any depth, rather than a
    request per level.

    The starting id is always included, which is what makes this usable as a
    cycle check: a proposed parent that appears in this list is the category
    itself or one of its own descendants.
    """
    anchor = select(Category.id).where(Category.id == category_id)
    subtree = anchor.cte(name="subtree", recursive=True)
    subtree = subtree.union_all(
        select(Category.id).join(subtree, Category.parent_id == subtree.c.id)
    )
    return list(db.scalars(select(subtree.c.id)))
