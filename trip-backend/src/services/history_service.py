"""History service (business logic)"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from src.models.trip import Trip
from src.schemas.history import TripResponse
from src.exceptions import NotFoundException


class HistoryService:
    """History service (business logic)"""
    
    @staticmethod
    async def get_trips(
        db: AsyncSession, 
        user_id: int, 
        page: int = 1, 
        page_size: int = 20
    ) -> tuple:
        """获取行程历史列表（分页）
        
        Args:
            db: Database session
            user_id: User ID
            page: Page number (1-based)
            page_size: Page size
            
        Returns:
            tuple: (trips, total)
        """
        # 1. Build base query (exclude parent trips - only show root trips)
        query = select(Trip).where(
            Trip.user_id == user_id
        ).order_by(Trip.created_at.desc())
        
        # 2. Get total count
        count_query = select(func.count()).select_from(
            select(Trip).where(Trip.user_id == user_id).subquery()
        )
        total = await db.scalar(count_query)
        
        # 3. Get paginated results
        offset = (page - 1) * page_size
        result = await db.execute(
            query.offset(offset).limit(page_size)
        )
        trips = result.scalars().all()
        
        return trips, total
    
    @staticmethod
    async def get_trip(
        db: AsyncSession, 
        trip_id: int, 
        user_id: int
    ) -> Trip:
        """获取单个行程详情
        
        Args:
            db: Database session
            trip_id: Trip ID
            user_id: User ID (for authorization)
            
        Returns:
            Trip: Trip object
            
        Raises:
            NotFoundException: if trip not found or doesn't belong to user
        """
        result = await db.execute(
            select(Trip).where(
                Trip.id == trip_id,
                Trip.user_id == user_id
            )
        )
        trip = result.scalar_one_or_none()
        
        if not trip:
            raise NotFoundException("行程")
        
        return trip
    
    @staticmethod
    async def get_trip_versions(
        db: AsyncSession,
        trip_id: int,
        user_id: int,
    ) -> list[Trip]:
        """获取行程的完整版本链（V1…Vn）

        从 trip_id 沿 parent_trip_id 回溯到根，再从根逐层收集全部子版本
        （同层按 created_at 升序展平）。深度上限 20，防脏数据成环。

        Args:
            db: Database session
            trip_id: Trip ID（链中任意节点）
            user_id: User ID (for authorization)

        Returns:
            list[Trip]: 按版本顺序（根在前）的行程列表

        Raises:
            NotFoundException: if trip not found or doesn't belong to user
        """
        trip = await HistoryService.get_trip(db, trip_id, user_id)

        # 1. 向上回溯到根（带深度上限 + 成环防护）
        visited = {trip.id}
        root = trip
        for _ in range(20):
            if not root.parent_trip_id:
                break
            result = await db.execute(
                select(Trip).where(
                    Trip.id == root.parent_trip_id,
                    Trip.user_id == user_id,
                )
            )
            parent = result.scalar_one_or_none()
            if not parent or parent.id in visited:
                break
            visited.add(parent.id)
            root = parent

        # 2. 从根逐层向下收集（同层按 created_at 升序）
        versions: list[Trip] = [root]
        collected = {root.id}
        frontier = [root.id]
        for _ in range(20):
            if not frontier:
                break
            result = await db.execute(
                select(Trip)
                .where(
                    Trip.parent_trip_id.in_(frontier),
                    Trip.user_id == user_id,
                )
                .order_by(Trip.created_at.asc())
            )
            children = [c for c in result.scalars().all() if c.id not in collected]
            if not children:
                break
            versions.extend(children)
            collected.update(c.id for c in children)
            frontier = [c.id for c in children]

        return versions
    
    @staticmethod
    async def delete_trip(
        db: AsyncSession, 
        trip_id: int, 
        user_id: int
    ) -> bool:
        """删除行程
        
        Args:
            db: Database session
            trip_id: Trip ID
            user_id: User ID (for authorization)
            
        Returns:
            bool: True if successful
            
        Raises:
            NotFoundException: if trip not found or doesn't belong to user
        """
        # 1. Find trip
        result = await db.execute(
            select(Trip).where(
                Trip.id == trip_id,
                Trip.user_id == user_id
            )
        )
        trip = result.scalar_one_or_none()
        
        if not trip:
            raise NotFoundException("行程")
        
        # 2. Delete trip (cascade will delete child trips, conversations, messages, agent_steps)
        await db.delete(trip)
        await db.commit()
        
        return True
