# A/B 阶段代码审查报告

> **日期**：2026-08-01
> **审查范围**：A1-A4 工程基建、B1-B7 用户/CRUD 模块
> **代码量**：约 4500 行 Java 代码

---

## 🔴 严重问题（P0 - 必须立即修复）

### 1. **JWT 生成未实现**（B1）

**位置**：`UserController.java:75`

```java
String token = "mock-jwt-token-" + user.getId(); // 临时占位
```

**问题**：
- 登录接口返回伪造 token，无法通过 JwtAuthFilter 验证
- `@RequestAttribute("userId")` 在所有 JWT 保护接口中会为 null
- 导致所有需要认证的接口（B2-B7）实际处于**未保护状态**

**影响**：
- GET /api/user/info 会抛 NPE（userId=null）
- 所有 Admin 接口（hasRole('ADMIN')）无法工作
- 整个认证体系失效

**修复**：
```java
// UserController.java login 方法
String token = jwtUtil.generateToken(user.getUsername(), user.getId(),
    user.getRoleId != null ? user.getRoleId() : 2);

// JwtAuthFilter 需设置 request attribute
request.setAttribute("userId", userId);
request.setAttribute("roleId", roleId);
```

---

### 2. **RoleRepository 缺少 findByName 方法**（B1）

**位置**：`UserService.java:57`

```java
Role userRole = roleRepository.findByName("USER")
    .orElseThrow(() -> AppException.internalServerError("默认角色不存在"));
```

**问题**：
- `RoleRepository` 接口未定义 `findByName` 方法
- 编译失败

**修复**：
```java
// RoleRepository.java 添加
Optional<Role> findByName(String name);
```

---

### 3. **FormatResolver 引入缺失**（A1）

**位置**：`GlobalExceptionHandler.java`

**问题**：
- 使用了 `FormatResolver` 但未在 pom.xml 声明（实际已声明，但需验证）

---

### 4. **Date 类型不匹配**（A3）

**位置**：`User.java` 等实体

**问题**：
- `PasswordReset.expiresAt` 使用 `OffsetDateTime`
- `PasswordResetRepository.findByToken` 返回 `Optional<PasswordReset>`
- `UserService.resetPassword` 调用 `reset.isValid()` 会进行时间比较

**风险**：
- 数据库 `expires_at` 为 `timestamp with time zone`
- JPA `OffsetDateTime` 映射正确，但需验证时区处理

---

### 5. **BCrypt 密码验证未处理 null**（B1）

**位置**：`UserService.java:77`

```java
if (!passwordHasher.verify(password, user.getPassword())) {
```

**问题**：
- `user.getPassword()` 可能为 null（如果密码字段为空）
- `BCrypt.checkpw(null, hash)` 会抛 NPE

**修复**：
```java
if (user.getPassword() == null || !passwordHasher.verify(password, user.getPassword())) {
    throw AppException.unauthorized("密码错误");
}
```

---

### 6. **Message 实体缺少 conversationId 关联验证**（B2）

**位置**：`ConversationService.java:getConversation`

**问题**：
- 返回 `ConversationWithMessages` 但未验证消息归属
- 应级联查询 `conversation_id` 过滤

---

## 🟠 高优先级问题（P1）

### 7. **事务管理缺失**（全阶段）

**问题**：
- 所有 Service 方法无 `@Transactional` 注解
- 注册/修改密码等写操作需事务保证原子性
- 可能产生脏数据

**示例**：
```java
// UserService.java:91-101
public void changePassword(Long userId, String oldPassword, String newPassword) {
    User user = userRepository.findById(userId)...;
    if (!passwordHasher.verify(oldPassword, user.getPassword()))...;
    user.setPassword(passwordHasher.hash(newPassword));
    userRepository.save(user); // 无事务，可能中间失败
}
```

**修复**：
```java
@Transactional(rollbackFor = Exception.class)
public void changePassword(Long userId, String oldPassword, String newPassword) {
    // ...
}
```

---

### 8. **SQL 注入风险**（B6）

**位置**：`AmapClient.java:geocode`

```java
ResponseEntity<JsonNode> response = restTemplate.exchange(
    url + "?key=" + apiKey + "&address=" + address, // 直接拼接
    HttpMethod.GET, entity, JsonNode.class);
```

**问题**：
- `address` 参数直接拼接到 URL，可能含特殊字符
- 应使用 `UriComponentsBuilder` 编码

**修复**：
```java
import org.springframework.web.util.UriComponentsBuilder;

String url = UriComponentsBuilder.fromHttpUrl(baseUrl + "/geocode/geo")
    .queryParam("key", apiKey)
    .queryParam("address", address)
    .encode()
    .toUriString();
```

---

### 9. **@RequestAttribute("userId") 无法工作**（全阶段）

**位置**：所有 `@PreAuthorize("isAuthenticated()")` 接口

**问题**：
- `@RequestAttribute` 需在 Filter 中 `request.setAttribute("userId", value)` 设置
- 当前 `JwtAuthFilter` 仅设置 `SecurityContextHolder`，未设置 request attribute
- 导致 `@RequestAttribute("userId")` 为 null

**修复**（JwtAuthFilter.java）：
```java
// 在验证成功后
Long userId = ((Number) claims.get("userId")).longValue();
request.setAttribute("userId", userId); // 添加这行
request.setAttribute("roleId", ((Number) claims.get("roleId")).intValue());
```

---

### 10. **RateLimiter 缺少 userId 提取**（A2）

**位置**：`GlobalRateLimitFilter.java:extractRateLimitKey`

```java
private String extractRateLimitKey(HttpServletRequest request) {
    // TODO: 从 JWT 或 session 提取 userId
    return request.getRemoteAddr();
}
```

**问题**：
- 暂时返回 IP，后续需从 JWT 提取 userId
- 限流失效（用户可绕过）

---

### 11. **缺少 @EnableJpaRepositories 的 enableDefaultAuditing**（A3）

**问题**：
- `@CreatedDate` / `@LastModifiedDate` 未启用自动填充
- 当前手动在 `@PrePersist` / `@PreUpdate` 中处理，可工作但不够优雅

---

## 🟡 中优先级问题（P2）

### 12. **角色名硬编码**（B1）

**位置**：`UserService.java:57`

```java
Role userRole = roleRepository.findByName("USER")
```

**问题**：
- 假设数据库已存在 "USER" 角色
- 初始化数据未处理

**建议**：
- 添加 `data.sql` 或 `CommandLineRunner` 插入默认角色

---

### 13. **PasswordResetRepository 缺少过期清理**（B1）

**位置**：`PasswordResetRepository.java`

**问题**：
- 定时任务未实现，`expired` 令牌会堆积
- 应添加 `@Scheduled` 清理

---

### 14. **Spots/SpotDocs 分页未处理空结果**（B3）

**位置**：`KnowledgeService.java:getSpots`

```java
Page<Spot> spots = spotRepository.findByCityAndCategory(city, category, pageable);
List<Map<String, Object>> items = spots.getContent().stream()...
```

**问题**：
- `city` 和 `category` 为空时，方法可能返回全部数据
- 应添加参数校验

---

### 15. **FeedbackController 评分校验不完整**（B4）

**位置**：`FeedbackController.java:SubmitFeedbackRequest`

```java
@Min(1) @Max(-1) Integer rating  // 错误！
```

**问题**：
- JSR-380 `@Min`/`@Max` 不支持负值
- 应自定义校验器或使用 `@Pattern(regexp="[-1]|[1]")`

---

### 16. **GzipFilter 响应包装器重复添加 Header**（A2）

**位置**：`GzipFilter.java:setHeader`

```java
@Override
public void setHeader(String name, String value) {
    if (RESPONSE_HEADER_CONTENT_ENCODING.equalsIgnoreCase(name)) {
        return; // 忽略 Content-Encoding
    }
    super.setHeader(name, value); // 可能重复调用
}
```

**问题**：
- 需处理 `addHeader` 方法
- Content-Length 头需移除（Gzip 后长度变化）

---

### 17. **IdempotencyFilter 未清理超限条目**（B7）

**位置**：`IdempotencyFilter.java:74-76`

```java
if (cache.size() > MAX_ENTRIES) {
    cache.clear(); // 暴力清空，应使用 LRU
}
```

**问题**：
- 超过阈值直接清空，导致其他请求失效
- 应实现 LRU 或定时清理

---

### 18. **TripService 版本链逻辑不正确**（B2）

**位置**：`TripService.java:getTripVersions`

```java
if (trip.getParentTripId() != null) {
    versions.addAll(tripRepository.findByIdAndUserId(trip.getParentTripId(), userId)
        .map(List::of)
        .orElse(List.of()));
}
```

**问题**：
- 仅查询父版本，未查询所有后代版本
- 应使用 `findAllByParentTripId`

---

## 🟢 低优先级问题（P3）

### 19. **缺少统一响应格式工具类**

**问题**：
- 所有 Controller 重复 `Map.of("code", 200, "data", ...)`
- 应抽取 `ResponseBuilder` 或 `ApiResponse` 类

---

### 20. **异常消息硬编码中文**（全局）

**问题**：
- `AppException.badRequest("用户名已存在")`
- 后续国际化困难

---

### 21. **缺少日志**

**问题**：
- Service 层无任何日志
- 排查问题困难

---

### 22. **@PreAuthorize 无法使用 SpEL 表达式**

**位置**：所有 Controller

**问题**：
- `@PreAuthorize("isAuthenticated()")` 需配合 Spring Security 配置
- 当前无 SecurityConfiguration 类

---

## ✅ 良好实践

1. ✅ **分层清晰**：Controller → Service → Repository
2. ✅ **DTO 使用 Record**：类型安全、不可变
3. ✅ **接口定义清晰**：CacheBackend、Embedder、Reranker 等
4. ✅ **降级策略**：内存缓存、Passthrough 实现
5. ✅ **配置外部化**：application.yml
6. ✅ **幂等键设计合理**：`{userId or anon}:{key}`
7. ✅ **并发守卫非阻塞**：`tryAcquire` 避免死锁

---

## 📊 统计

| 等级 | 数量 | 说明 |
|------|------|------|
| 🔴 P0 | 6 | 必须立即修复，阻塞后续开发 |
| 🟠 P1 | 5 | 高优先级，影响核心功能 |
| 🟡 P2 | 7 | 中优先级，建议修复 |
| 🟢 P3 | 4 | 低优先级，优化项 |

---

## 🎯 立即行动清单

1. **实现 JwtUtil.generateToken() 并修复 JwtAuthFilter**
2. **添加 RoleRepository.findByName()**
3. **修复 @RequestAttribute 设置**
4. **添加 @Transactional 到所有写操作**
5. **修复 BCrypt null 处理**
6. **使用 UriComponentsBuilder 编码 URL**
7. **创建 SecurityConfiguration 类**
8. **添加 data.sql 默认角色**

---

**建议**：优先修复 P0 问题后再继续 D 阶段开发，否则后续测试全部失败。
