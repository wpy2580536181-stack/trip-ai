<template>
  <div v-if="tripData" class="print-view">
    <!-- 1. Header -->
    <header class="print-header">
      <h1>{{ tripData.city }} · {{ tripData.days }}天行程</h1>
      <div class="meta">
        <span class="budget">预算: ¥{{ tripData.totalBudget.toLocaleString() }}</span>
        <span class="export-time">导出时间: {{ formatNow() }}</span>
      </div>
    </header>

    <!-- 2. Daily itinerary -->
    <section
      v-for="day in tripData.dailyItinerary"
      :key="day.day"
      class="day-section"
    >
      <h2 class="day-title">
        第 {{ day.day }} 天
        <span v-if="day.date" class="day-date">{{ day.date }}</span>
      </h2>

      <div class="slot morning">
        <div class="slot-label">上午</div>
        <div class="slot-content">
          <img v-if="day.morning.imageUrl" :src="day.morning.imageUrl" :alt="day.morning.spot" class="print-spot-image" />
          <h3 class="spot-name">{{ day.morning.spot || '待定' }}</h3>
          <div class="slot-meta">
            <span v-if="day.morning.duration">⏱ {{ day.morning.duration }}</span>
            <span v-if="day.morning.ticket">🎫 {{ day.morning.ticket }}</span>
            <span v-if="day.morning.transportation">🚗 {{ day.morning.transportation }}</span>
          </div>
          <p v-if="day.morning.description" class="slot-desc">{{ day.morning.description }}</p>
        </div>
      </div>

      <div class="slot afternoon">
        <div class="slot-label">下午</div>
        <div class="slot-content">
          <img v-if="day.afternoon.imageUrl" :src="day.afternoon.imageUrl" :alt="day.afternoon.spot" class="print-spot-image" />
          <h3 class="spot-name">{{ day.afternoon.spot || '待定' }}</h3>
          <div class="slot-meta">
            <span v-if="day.afternoon.duration">⏱ {{ day.afternoon.duration }}</span>
            <span v-if="day.afternoon.ticket">🎫 {{ day.afternoon.ticket }}</span>
            <span v-if="day.afternoon.transportation">🚗 {{ day.afternoon.transportation }}</span>
          </div>
          <p v-if="day.afternoon.description" class="slot-desc">{{ day.afternoon.description }}</p>
        </div>
      </div>

      <div class="slot evening">
        <div class="slot-label">晚上</div>
        <div class="slot-content">
          <img v-if="day.evening.imageUrl" :src="day.evening.imageUrl" :alt="day.evening.spot" class="print-spot-image" />
          <h3 class="spot-name">{{ day.evening.spot || '待定' }}</h3>
          <div class="slot-meta">
            <span v-if="day.evening.duration">⏱ {{ day.evening.duration }}</span>
            <span v-if="day.evening.ticket">🎫 {{ day.evening.ticket }}</span>
            <span v-if="day.evening.transportation">🚗 {{ day.evening.transportation }}</span>
          </div>
          <p v-if="day.evening.description" class="slot-desc">{{ day.evening.description }}</p>
        </div>
      </div>

      <div v-if="day.breakfast || day.lunch || day.dinner" class="meals-section">
        <div class="section-subtitle">🍽 餐饮推荐</div>
        <div v-if="day.breakfast" class="slot meal">
          <div class="slot-label">早餐</div>
          <div class="slot-content">
            <h3 class="spot-name">{{ day.breakfast.spot }}</h3>
            <p v-if="day.breakfast.description" class="slot-desc">{{ day.breakfast.description }}</p>
          </div>
        </div>
        <div v-if="day.lunch" class="slot meal">
          <div class="slot-label">午餐</div>
          <div class="slot-content">
            <h3 class="spot-name">{{ day.lunch.spot }}</h3>
            <p v-if="day.lunch.description" class="slot-desc">{{ day.lunch.description }}</p>
          </div>
        </div>
        <div v-if="day.dinner" class="slot meal">
          <div class="slot-label">晚餐</div>
          <div class="slot-content">
            <h3 class="spot-name">{{ day.dinner.spot }}</h3>
            <p v-if="day.dinner.description" class="slot-desc">{{ day.dinner.description }}</p>
          </div>
        </div>
      </div>

      <div v-if="day.accommodation" class="hotel-section">
        <div class="section-subtitle">🏨 住宿推荐</div>
        <div class="slot hotel">
          <div class="slot-label">住宿</div>
          <div class="slot-content">
            <h3 class="spot-name">{{ day.accommodation.spot }}</h3>
            <div class="slot-meta">
              <span v-if="day.accommodation.duration">💰 {{ day.accommodation.duration }}</span>
              <span v-if="day.accommodation.ticket">🎫 {{ day.accommodation.ticket }}</span>
              <span v-if="day.accommodation.transportation">🚗 {{ day.accommodation.transportation }}</span>
            </div>
            <p v-if="day.accommodation.description" class="slot-desc">{{ day.accommodation.description }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 3. Budget breakdown -->
    <section class="budget-section">
      <h2 class="section-title">预算明细</h2>
      <table class="budget-table">
        <thead>
          <tr><th>项目</th><th>金额 (¥)</th></tr>
        </thead>
        <tbody>
          <tr><td>住宿</td><td>{{ tripData.budgetBreakdown.accommodation.toLocaleString() }}</td></tr>
          <tr><td>餐饮</td><td>{{ tripData.budgetBreakdown.food.toLocaleString() }}</td></tr>
          <tr><td>交通</td><td>{{ tripData.budgetBreakdown.transportation.toLocaleString() }}</td></tr>
          <tr><td>门票</td><td>{{ tripData.budgetBreakdown.tickets.toLocaleString() }}</td></tr>
          <tr><td>其他</td><td>{{ tripData.budgetBreakdown.other.toLocaleString() }}</td></tr>
          <tr class="total">
            <td>总计</td><td>¥{{ tripData.totalBudget.toLocaleString() }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 4. Tips -->
    <section v-if="tripData.tips.length > 0" class="tips-section">
      <h2 class="section-title">出行Tips</h2>
      <ul class="tips-list">
        <li v-for="(tip, i) in tripData.tips" :key="i">{{ tip }}</li>
      </ul>
    </section>

    <!-- 5. Warnings -->
    <section v-if="tripData.warnings && tripData.warnings.length > 0" class="warnings-section">
      <h2 class="section-title">⚠️ 注意事项</h2>
      <ul class="warnings-list">
        <li v-for="(w, i) in tripData.warnings" :key="i">{{ w }}</li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface TripSlot {
  spot: string
  duration?: string
  ticket?: string
  transportation?: string
  description?: string
  imageUrl?: string
  latitude?: number
  longitude?: number
}

interface TripDay {
  day: number
  date?: string
  morning: TripSlot
  afternoon: TripSlot
  evening: TripSlot
  breakfast?: TripSlot
  lunch?: TripSlot
  dinner?: TripSlot
  accommodation?: TripSlot
}

interface BudgetBreakdown {
  accommodation: number
  food: number
  transportation: number
  tickets: number
  other: number
}

interface TripContent {
  city: string
  days: number
  totalBudget: number
  dailyItinerary: TripDay[]
  budgetBreakdown: BudgetBreakdown
  tips: string[]
  warnings?: string[]
}

const props = defineProps<{
  tripData: TripContent | null
}>()

function formatNow(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
}

const budgetSum = computed(() => {
  if (!props.tripData) return 0
  const b = props.tripData.budgetBreakdown
  return b.accommodation + b.food + b.transportation + b.tickets + b.other
})
</script>

<style>
.print-view {
  width: 794px;
  min-height: 1123px;
  padding: 40px;
  background: #ffffff;
  color: #333;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', sans-serif;
  font-size: 14px;
  line-height: 1.6;
}

.print-header {
  text-align: center;
  padding-bottom: 20px;
  margin-bottom: 30px;
  border-bottom: 2px solid #333;
}
.print-header h1 {
  font-size: 24px;
  margin: 0 0 8px 0;
  color: #000;
}
.print-header .meta {
  font-size: 12px;
  color: #666;
  display: flex;
  justify-content: center;
  gap: 20px;
}
.print-header .budget {
  color: #e74c3c;
  font-weight: 600;
}

.day-section {
  margin-bottom: 30px;
  page-break-inside: avoid;
}
.day-title {
  font-size: 18px;
  margin: 0 0 12px 0;
  padding: 6px 12px;
  background: #f5f5f5;
  border-left: 4px solid #1976d2;
  color: #000;
}
.day-date {
  font-size: 13px;
  color: #666;
  margin-left: 8px;
  font-weight: normal;
}

.slot {
  display: flex;
  margin-bottom: 10px;
  padding: 10px;
  border-radius: 4px;
}
.slot.morning { background: #fff7e6; border-left: 3px solid #fa8c16; }
.slot.afternoon { background: #e6f7ff; border-left: 3px solid #1890ff; }
.slot.evening { background: #f6ffed; border-left: 3px solid #52c41a; }
.slot.meal { background: #fff0f6; border-left: 3px solid #eb2f96; }
.slot.hotel { background: #f9f0ff; border-left: 3px solid #722ed1; }

.slot-label {
  flex-shrink: 0;
  width: 50px;
  font-size: 12px;
  font-weight: 600;
  padding-top: 2px;
}
.slot.morning .slot-label { color: #fa8c16; }
.slot.afternoon .slot-label { color: #1890ff; }
.slot.evening .slot-label { color: #52c41a; }
.slot.meal .slot-label { color: #eb2f96; }
.slot.hotel .slot-label { color: #722ed1; }

.slot-content {
  flex: 1;
}
.spot-name {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px 0;
  color: #000;
}
.slot-meta {
  font-size: 12px;
  color: #666;
  margin-bottom: 4px;
}
.slot-meta span {
  margin-right: 12px;
}
.slot-desc {
  font-size: 12px;
  color: #555;
  margin: 4px 0 0 0;
}

.print-spot-image {
  width: 100%;
  height: 140px;
  object-fit: cover;
  border-radius: 4px;
  margin-bottom: 6px;
}

.budget-section {
  margin-top: 30px;
  page-break-inside: avoid;
}
.section-title {
  font-size: 16px;
  margin: 0 0 12px 0;
  padding-bottom: 6px;
  border-bottom: 1px solid #ddd;
  color: #000;
}
.section-subtitle {
  font-size: 14px;
  margin: 16px 0 8px;
  padding: 4px 8px;
  background: #f5f5f5;
  border-radius: 4px;
  color: #333;
}
.budget-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.budget-table th,
.budget-table td {
  padding: 8px 12px;
  border: 1px solid #ddd;
  text-align: left;
}
.budget-table th {
  background: #f5f5f5;
  font-weight: 600;
}
.budget-table td:last-child {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.budget-table .total {
  font-weight: 600;
  background: #fafafa;
}
.budget-table .total td {
  border-top: 2px solid #333;
}

.tips-section,
.warnings-section {
  margin-top: 20px;
  page-break-inside: avoid;
}
.tips-list,
.warnings-list {
  padding-left: 20px;
  margin: 0;
}
.tips-list li,
.warnings-list li {
  margin-bottom: 6px;
  font-size: 13px;
}
.warnings-section {
  color: #d46b08;
}
.warnings-list li {
  list-style-type: '⚠ ';
}
</style>
