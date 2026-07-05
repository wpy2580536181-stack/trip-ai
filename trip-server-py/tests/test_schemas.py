"""Schema 验证测试。

覆盖 src/schemas/ 下所有 Pydantic schema 的：
- 正常输入验证通过
- 必填字段缺失 → ValidationError
- 类型错误 → ValidationError
- 边界值（空字符串、超长、负数等）
- 可选字段缺省值
- 嵌套 schema 验证
"""

from __future__ import annotations

import pytest
from datetime import datetime
from pydantic import ValidationError


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  conversation.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from src.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationListResponse,
)


class TestConversationCreate:
    def test_valid(self):
        obj = ConversationCreate(title="测试对话")
        assert obj.title == "测试对话"
        assert obj.model == "deepseek-chat"  # 默认值

    def test_valid_with_model(self):
        obj = ConversationCreate(title="对话", model="gpt-4")
        assert obj.model == "gpt-4"

    def test_missing_title(self):
        with pytest.raises(ValidationError):
            ConversationCreate()  # type: ignore[call-arg]

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            ConversationCreate(title="x" * 256)

    def test_title_max_length(self):
        obj = ConversationCreate(title="x" * 255)
        assert len(obj.title) == 255

    def test_model_too_long(self):
        with pytest.raises(ValidationError):
            ConversationCreate(title="t", model="x" * 101)

    def test_default_model(self):
        obj = ConversationCreate(title="t")
        assert obj.model == "deepseek-chat"


class TestConversationResponse:
    def test_valid(self):
        data = {
            "id": 1,
            "userId": 10,
            "title": "test",
            "createdAt": "2026-01-01T00:00:00",
        }
        obj = ConversationResponse.model_validate(data)
        assert obj.id == 1
        assert obj.user_id == 10
        assert obj.summary is None

    def test_missing_required_id(self):
        with pytest.raises(ValidationError):
            ConversationResponse.model_validate({
                "userId": 10,
                "title": "t",
                "createdAt": "2026-01-01T00:00:00",
            })

    def test_missing_required_title(self):
        with pytest.raises(ValidationError):
            ConversationResponse.model_validate({
                "id": 1,
                "userId": 10,
                "createdAt": "2026-01-01T00:00:00",
            })

    def test_optional_fields_default_none(self):
        data = {
            "id": 1,
            "userId": 1,
            "title": "t",
            "createdAt": "2026-01-01T00:00:00",
        }
        obj = ConversationResponse.model_validate(data)
        assert obj.summary is None
        assert obj.summary_error is None
        assert obj.summary_at is None
        assert obj.updated_at is None
        assert obj.count is None


class TestConversationListResponse:
    def test_valid(self):
        data = {
            "items": [{
                "id": 1,
                "userId": 1,
                "title": "t",
                "createdAt": "2026-01-01T00:00:00",
            }],
            "total": 1,
            "page": 1,
            "pageSize": 10,
        }
        obj = ConversationListResponse.model_validate(data)
        assert obj.total == 1
        assert len(obj.items) == 1

    def test_empty_items(self):
        data = {"items": [], "total": 0, "page": 1, "pageSize": 10}
        obj = ConversationListResponse.model_validate(data)
        assert obj.items == []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  history.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from src.schemas.history import TripResponse as HistoryTripResponse, TripListResponse


class TestHistoryTripResponse:
    def test_valid(self):
        data = {
            "id": 1,
            "userId": 10,
            "city": "北京",
            "days": 3,
            "budget": 5000,
            "content": {"day1": "故宫"},
            "createdAt": "2026-01-01T00:00:00",
        }
        obj = HistoryTripResponse.model_validate(data)
        assert obj.city == "北京"
        assert obj.status == "completed"
        assert obj.from_city is None
        assert obj.parent_trip_id is None

    def test_missing_required_city(self):
        with pytest.raises(ValidationError):
            HistoryTripResponse.model_validate({
                "id": 1, "userId": 1, "days": 1,
                "budget": 100, "content": {}, "createdAt": "2026-01-01T00:00:00",
            })

    def test_missing_required_budget(self):
        with pytest.raises(ValidationError):
            HistoryTripResponse.model_validate({
                "id": 1, "userId": 1, "city": "北京",
                "days": 1, "content": {}, "createdAt": "2026-01-01T00:00:00",
            })

    def test_type_error_days_string(self):
        with pytest.raises(ValidationError):
            HistoryTripResponse.model_validate({
                "id": 1, "userId": 1, "city": "北京",
                "days": "abc", "budget": 100,
                "content": {}, "createdAt": "2026-01-01T00:00:00",
            })

    def test_optional_defaults(self):
        data = {
            "id": 1, "userId": 1, "city": "上海",
            "days": 2, "budget": 3000, "content": {},
            "createdAt": "2026-01-01T00:00:00",
        }
        obj = HistoryTripResponse.model_validate(data)
        assert obj.from_city is None
        assert obj.parent_trip_id is None
        assert obj.updated_at is None


class TestTripListResponse:
    def test_valid(self):
        data = {
            "items": [{
                "id": 1, "userId": 1, "city": "北京",
                "days": 3, "budget": 5000, "content": {},
                "createdAt": "2026-01-01T00:00:00",
            }],
            "total": 1, "page": 1, "pageSize": 20,
        }
        obj = TripListResponse.model_validate(data)
        assert obj.total == 1
        assert len(obj.items) == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  knowledge.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from src.schemas.knowledge import (
    SpotResponse,
    SpotCreate,
    SpotUpdate,
    SpotListResponse,
)


class TestSpotCreate:
    def test_valid(self):
        obj = SpotCreate(
            name="故宫", city="北京", category="历史",
            description="明清皇宫",
        )
        assert obj.name == "故宫"
        assert obj.tags == []  # 默认空列表
        assert obj.avg_cost is None

    def test_valid_full(self):
        obj = SpotCreate(
            name="故宫", city="北京", category="历史",
            description="明清皇宫", tags=["5A", "世界遗产"],
            avgCost=60.0, duration="3小时",
            openTime="08:30-17:00", rating=4.8,
        )
        assert len(obj.tags) == 2
        assert obj.avg_cost == 60.0

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            SpotCreate(city="北京", category="历史", description="test")  # type: ignore[call-arg]

    def test_missing_city(self):
        with pytest.raises(ValidationError):
            SpotCreate(name="故宫", category="历史", description="test")  # type: ignore[call-arg]

    def test_missing_category(self):
        with pytest.raises(ValidationError):
            SpotCreate(name="故宫", city="北京", description="test")  # type: ignore[call-arg]

    def test_missing_description(self):
        with pytest.raises(ValidationError):
            SpotCreate(name="故宫", city="北京", category="历史")  # type: ignore[call-arg]

    def test_default_tags_empty(self):
        obj = SpotCreate(name="x", city="y", category="z", description="d")
        assert obj.tags == []

    def test_optional_avg_cost_default_none(self):
        obj = SpotCreate(name="x", city="y", category="z", description="d")
        assert obj.avg_cost is None
        assert obj.duration is None
        assert obj.open_time is None
        assert obj.rating is None


class TestSpotUpdate:
    def test_all_optional(self):
        obj = SpotUpdate()
        assert obj.name is None
        assert obj.city is None
        assert obj.category is None
        assert obj.description is None
        assert obj.tags is None

    def test_partial_update(self):
        obj = SpotUpdate(name="新名字", rating=4.5)
        assert obj.name == "新名字"
        assert obj.rating == 4.5
        assert obj.city is None


class TestSpotResponse:
    def test_valid(self):
        data = {
            "id": 1, "name": "故宫", "city": "北京",
            "category": "历史", "description": "明清皇宫",
            "tags": ["5A"],
        }
        obj = SpotResponse.model_validate(data)
        assert obj.avg_cost is None
        assert obj.vector_id is None

    def test_missing_required_name(self):
        with pytest.raises(ValidationError):
            SpotResponse.model_validate({
                "id": 1, "city": "北京", "category": "c",
                "description": "d", "tags": [],
            })

    def test_type_error_id_string(self):
        with pytest.raises(ValidationError):
            SpotResponse.model_validate({
                "id": "not_int", "name": "x", "city": "y",
                "category": "c", "description": "d", "tags": [],
            })


class TestSpotListResponse:
    def test_valid(self):
        data = {
            "items": [{
                "id": 1, "name": "x", "city": "y",
                "category": "c", "description": "d", "tags": [],
            }],
            "total": 1, "page": 1, "pageSize": 10,
        }
        obj = SpotListResponse.model_validate(data)
        assert obj.total == 1

    def test_empty(self):
        data = {"items": [], "total": 0, "page": 1, "pageSize": 10}
        obj = SpotListResponse.model_validate(data)
        assert obj.items == []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  trip.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from src.schemas.trip import (
    RecommendRequest,
    OptimizeRequest,
    ChatRequest,
    SpotSchema,
    DailyItinerarySchema,
    BudgetBreakdownSchema,
    TripDataResponse,
    TripResponse,
    ChatCompleteData,
)


class TestRecommendRequest:
    def test_valid(self):
        obj = RecommendRequest(city="北京", budget=5000, days=3)
        assert obj.city == "北京"
        assert obj.departure_city is None

    def test_valid_with_departure(self):
        obj = RecommendRequest(
            city="北京", budget=5000, days=3,
            departureCity="上海",
        )
        assert obj.departure_city == "上海"

    def test_missing_city(self):
        with pytest.raises(ValidationError):
            RecommendRequest(budget=5000, days=3)  # type: ignore[call-arg]

    def test_missing_budget(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", days=3)  # type: ignore[call-arg]

    def test_missing_days(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", budget=5000)  # type: ignore[call-arg]

    def test_budget_too_low(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", budget=10, days=3)

    def test_budget_too_high(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", budget=2_000_000, days=3)

    def test_days_zero(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", budget=5000, days=0)

    def test_days_too_many(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", budget=5000, days=31)

    def test_city_empty(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="", budget=5000, days=3)

    def test_city_too_long(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="x" * 51, budget=5000, days=3)

    def test_budget_boundary_min(self):
        obj = RecommendRequest(city="北京", budget=50, days=1)
        assert obj.budget == 50

    def test_budget_boundary_max(self):
        obj = RecommendRequest(city="北京", budget=1_000_000, days=30)
        assert obj.budget == 1_000_000

    def test_negative_budget(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", budget=-100, days=3)

    def test_budget_type_error(self):
        with pytest.raises(ValidationError):
            RecommendRequest(city="北京", budget="abc", days=3)  # type: ignore[arg-type]


class TestOptimizeRequest:
    def test_valid(self):
        obj = OptimizeRequest(tripId=1)
        assert obj.trip_id == 1
        assert obj.instruction is None

    def test_valid_with_instruction(self):
        obj = OptimizeRequest(tripId=1, instruction="减少预算")
        assert obj.instruction == "减少预算"

    def test_missing_trip_id(self):
        with pytest.raises(ValidationError):
            OptimizeRequest()  # type: ignore[call-arg]

    def test_trip_id_zero(self):
        with pytest.raises(ValidationError):
            OptimizeRequest(tripId=0)

    def test_trip_id_negative(self):
        with pytest.raises(ValidationError):
            OptimizeRequest(tripId=-1)

    def test_instruction_too_long(self):
        with pytest.raises(ValidationError):
            OptimizeRequest(tripId=1, instruction="x" * 1001)


class TestChatRequest:
    def test_valid(self):
        obj = ChatRequest(message="推荐北京景点")
        assert obj.conversation_id is None

    def test_valid_with_conversation(self):
        obj = ChatRequest(message="你好", conversationId=42)
        assert obj.conversation_id == 42

    def test_missing_message(self):
        with pytest.raises(ValidationError):
            ChatRequest()  # type: ignore[call-arg]

    def test_empty_message(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")


class TestSpotSchema:
    def test_valid_minimal(self):
        obj = SpotSchema(spot="故宫")
        assert obj.spot == "故宫"
        assert obj.duration is None
        assert obj.latitude is None
        assert obj.image_url is None

    def test_valid_full(self):
        obj = SpotSchema(
            spot="故宫", duration="3h", ticket="60元",
            transportation="地铁", description="皇宫",
            latitude=39.9, longitude=116.4,
            imageUrl="https://example.com/img.jpg",
        )
        assert obj.image_url == "https://example.com/img.jpg"

    def test_missing_spot(self):
        with pytest.raises(ValidationError):
            SpotSchema()  # type: ignore[call-arg]


class TestDailyItinerarySchema:
    """嵌套 schema 验证"""

    _spot = {"spot": "x"}

    def test_valid(self):
        data = {
            "day": 1,
            "morning": self._spot,
            "afternoon": self._spot,
            "evening": self._spot,
        }
        obj = DailyItinerarySchema.model_validate(data)
        assert obj.day == 1
        assert obj.breakfast is None
        assert obj.lunch is None
        assert obj.dinner is None
        assert obj.accommodation is None

    def test_valid_with_meals(self):
        data = {
            "day": 1,
            "morning": self._spot,
            "afternoon": self._spot,
            "evening": self._spot,
            "breakfast": self._spot,
            "lunch": self._spot,
            "dinner": self._spot,
            "accommodation": self._spot,
        }
        obj = DailyItinerarySchema.model_validate(data)
        assert obj.breakfast is not None
        assert obj.accommodation is not None

    def test_missing_morning(self):
        with pytest.raises(ValidationError):
            DailyItinerarySchema.model_validate({
                "day": 1,
                "afternoon": self._spot,
                "evening": self._spot,
            })

    def test_nested_invalid_spot(self):
        with pytest.raises(ValidationError):
            DailyItinerarySchema.model_validate({
                "day": 1,
                "morning": {},  # missing 'spot'
                "afternoon": self._spot,
                "evening": self._spot,
            })


class TestBudgetBreakdownSchema:
    def test_defaults(self):
        obj = BudgetBreakdownSchema()
        assert obj.accommodation == 0
        assert obj.food == 0
        assert obj.transportation == 0
        assert obj.tickets == 0
        assert obj.other == 0

    def test_valid(self):
        obj = BudgetBreakdownSchema(
            accommodation=1000, food=500,
            transportation=300, tickets=200, other=100,
        )
        assert obj.accommodation == 1000

    def test_negative_allowed(self):
        # Pydantic float 没有 ge 约束，负数在 schema 层不拦截
        obj = BudgetBreakdownSchema(accommodation=-100)
        assert obj.accommodation == -100


class TestTripDataResponse:
    def test_valid_minimal(self):
        obj = TripDataResponse(city="北京", days=3)
        assert obj.id is None
        assert obj.total_budget is None
        assert obj.daily_itinerary is None
        assert obj.tips is None

    def test_valid_full(self):
        data = {
            "id": 1, "city": "北京", "days": 3,
            "totalBudget": 5000.0,
            "dailyItinerary": [{"day": 1}],
            "budgetBreakdown": {"accommodation": 1000},
            "tips": ["带好身份证"],
            "warnings": ["暑期人多"],
        }
        obj = TripDataResponse.model_validate(data)
        assert obj.total_budget == 5000.0


class TestTripResponse:
    def test_valid(self):
        data = {
            "success": True,
            "data": {"city": "北京", "days": 3},
        }
        obj = TripResponse.model_validate(data)
        assert obj.success is True
        assert obj.data.city == "北京"

    def test_missing_success(self):
        with pytest.raises(ValidationError):
            TripResponse.model_validate({"data": {"city": "x", "days": 1}})

    def test_missing_data(self):
        with pytest.raises(ValidationError):
            TripResponse.model_validate({"success": True})


class TestChatCompleteData:
    def test_valid(self):
        obj = ChatCompleteData(conversationId=42)
        assert obj.conversation_id == 42
        assert obj.usage is None

    def test_with_usage(self):
        obj = ChatCompleteData(
            conversationId=1,
            usage={"total_tokens": 1000},
        )
        assert obj.usage == {"total_tokens": 1000}

    def test_missing_conversation_id(self):
        with pytest.raises(ValidationError):
            ChatCompleteData()  # type: ignore[call-arg]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  user.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from src.schemas.user import (
    UserRegister,
    UserLogin,
    UserResponse,
    LoginResponse,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    UserUpdateRequest,
    FeedbackCreate,
    FeedbackResponse,
)


class TestUserRegister:
    def test_valid(self):
        obj = UserRegister(
            username="testuser", email="test@example.com", password="123456",
        )
        assert obj.username == "testuser"

    def test_username_too_short(self):
        with pytest.raises(ValidationError):
            UserRegister(username="ab", email="a@b.com", password="123456")

    def test_username_too_long(self):
        with pytest.raises(ValidationError):
            UserRegister(username="x" * 51, email="a@b.com", password="123456")

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            UserRegister(username="test", email="a@b.com", password="12345")

    def test_password_too_long(self):
        with pytest.raises(ValidationError):
            UserRegister(username="test", email="a@b.com", password="x" * 51)

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserRegister(username="test", email="not-email", password="123456")

    def test_missing_username(self):
        with pytest.raises(ValidationError):
            UserRegister(email="a@b.com", password="123456")  # type: ignore[call-arg]

    def test_missing_email(self):
        with pytest.raises(ValidationError):
            UserRegister(username="test", password="123456")  # type: ignore[call-arg]

    def test_missing_password(self):
        with pytest.raises(ValidationError):
            UserRegister(username="test", email="a@b.com")  # type: ignore[call-arg]

    def test_boundary_username_min(self):
        obj = UserRegister(username="abc", email="a@b.com", password="123456")
        assert obj.username == "abc"

    def test_boundary_password_min(self):
        obj = UserRegister(username="test", email="a@b.com", password="123456")
        assert obj.password == "123456"


class TestUserLogin:
    def test_valid(self):
        obj = UserLogin(username="test", password="123456")
        assert obj.username == "test"

    def test_missing_username(self):
        with pytest.raises(ValidationError):
            UserLogin(password="123456")  # type: ignore[call-arg]

    def test_missing_password(self):
        with pytest.raises(ValidationError):
            UserLogin(username="test")  # type: ignore[call-arg]


class TestUserResponse:
    def test_valid(self):
        data = {
            "id": 1, "username": "test", "email": "a@b.com",
            "roleId": 1, "createdAt": "2026-01-01T00:00:00",
            "updatedAt": "2026-01-01T00:00:00",
        }
        obj = UserResponse.model_validate(data)
        assert obj.role_id == 1
        assert obj.status == 1
        assert obj.nickname is None
        assert obj.avatar is None
        assert obj.phone is None
        assert obj.bio is None

    def test_missing_required_email(self):
        with pytest.raises(ValidationError):
            UserResponse.model_validate({
                "id": 1, "username": "test",
                "roleId": 1, "createdAt": "2026-01-01T00:00:00",
                "updatedAt": "2026-01-01T00:00:00",
            })


class TestLoginResponse:
    def test_valid(self):
        data = {
            "id": 1, "username": "test", "email": "a@b.com",
            "roleId": 1, "token": "jwt-token-here",
        }
        obj = LoginResponse.model_validate(data)
        assert obj.token == "jwt-token-here"
        assert obj.nickname is None

    def test_missing_token(self):
        with pytest.raises(ValidationError):
            LoginResponse.model_validate({
                "id": 1, "username": "test",
                "email": "a@b.com", "roleId": 1,
            })


class TestChangePasswordRequest:
    def test_valid(self):
        obj = ChangePasswordRequest(oldPassword="old123", newPassword="new123456")
        assert obj.old_password == "old123"
        assert obj.new_password == "new123456"

    def test_new_password_too_short(self):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(oldPassword="old", newPassword="12345")

    def test_missing_old_password(self):
        with pytest.raises(ValidationError):
            ChangePasswordRequest(newPassword="123456")  # type: ignore[call-arg]


class TestForgotPasswordRequest:
    def test_valid(self):
        obj = ForgotPasswordRequest(email="test@example.com")
        assert obj.email == "test@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            ForgotPasswordRequest(email="bad")


class TestResetPasswordRequest:
    def test_valid(self):
        obj = ResetPasswordRequest(
            email="a@b.com", token="tok", newPassword="123456",
        )
        assert obj.new_password == "123456"

    def test_new_password_too_short(self):
        with pytest.raises(ValidationError):
            ResetPasswordRequest(
                email="a@b.com", token="tok", newPassword="12345",
            )

    def test_missing_token(self):
        with pytest.raises(ValidationError):
            ResetPasswordRequest(email="a@b.com", newPassword="123456")  # type: ignore[call-arg]


class TestUserUpdateRequest:
    def test_all_optional(self):
        obj = UserUpdateRequest()
        assert obj.nickname is None
        assert obj.avatar is None
        assert obj.phone is None
        assert obj.bio is None
        assert obj.preferences is None

    def test_partial(self):
        obj = UserUpdateRequest(nickname="新昵称", phone="13800001234")
        assert obj.nickname == "新昵称"
        assert obj.phone == "13800001234"

    def test_nickname_too_long(self):
        with pytest.raises(ValidationError):
            UserUpdateRequest(nickname="x" * 101)

    def test_phone_too_long(self):
        with pytest.raises(ValidationError):
            UserUpdateRequest(phone="x" * 21)


class TestFeedbackCreate:
    def test_valid(self):
        obj = FeedbackCreate(messageId=1, conversationId=2, rating=1)
        assert obj.rating == 1
        assert obj.comment is None
        assert obj.tags is None

    def test_valid_with_extras(self):
        obj = FeedbackCreate(
            messageId=1, conversationId=2, rating=-1,
            comment="不好", tags=["不准确"],
        )
        assert obj.comment == "不好"
        assert obj.tags == ["不准确"]

    def test_missing_message_id(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(conversationId=2, rating=1)  # type: ignore[call-arg]

    def test_missing_rating(self):
        with pytest.raises(ValidationError):
            FeedbackCreate(messageId=1, conversationId=2)  # type: ignore[call-arg]


class TestFeedbackResponse:
    def test_valid(self):
        obj = FeedbackResponse(id=1, rating=1)
        assert obj.id == 1

    def test_missing_id(self):
        with pytest.raises(ValidationError):
            FeedbackResponse(rating=1)  # type: ignore[call-arg]

    def test_missing_rating(self):
        with pytest.raises(ValidationError):
            FeedbackResponse(id=1)  # type: ignore[call-arg]
