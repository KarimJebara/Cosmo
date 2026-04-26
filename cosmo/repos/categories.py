from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from cosmo.models import Category


class CategoryRepo:
    def __init__(self, session: Session) -> None:
        self._s = session

    def list_for_user(
        self, user_id: int, *, type: str | None = None, include_archived: bool = False
    ) -> Sequence[Category]:
        stmt = select(Category).where(Category.user_id == user_id)
        if type is not None:
            stmt = stmt.where(Category.type == type)
        if not include_archived:
            stmt = stmt.where(Category.archived.is_(False))
        return self._s.execute(stmt.order_by(Category.name)).scalars().all()

    def get(self, category_id: int, user_id: int) -> Category | None:
        stmt = select(Category).where(
            Category.id == category_id, Category.user_id == user_id
        )
        return self._s.execute(stmt).scalar_one_or_none()

    def get_by_name(self, user_id: int, name: str, type: str) -> Category | None:
        stmt = select(Category).where(
            Category.user_id == user_id,
            Category.name == name,
            Category.type == type,
        )
        return self._s.execute(stmt).scalar_one_or_none()

    def get_or_create(self, user_id: int, name: str, type: str) -> Category:
        existing = self.get_by_name(user_id, name, type)
        if existing is not None:
            return existing
        category = Category(user_id=user_id, name=name, type=type)
        self._s.add(category)
        self._s.flush()
        return category

    def archive(self, category_id: int, user_id: int) -> bool:
        category = self.get(category_id, user_id)
        if category is None:
            return False
        category.archived = True
        return True
