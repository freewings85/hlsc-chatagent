"""
searchcoupons 场景测试用例设计
覆盖：明确项目查优惠、无项目查优惠、semantic_query 多轮累积、没查到商户优惠、apply_coupon 流程、
城市筛选、排序、模糊查询、预订引导、位置相关查询
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TestCase:
    """测试用例结构"""
    case_id: str
    title: str
    description: str
    user_input: str
    expected_behavior: str
    expected_tool_calls: list[dict]
    expected_output_type: str  # text / spec / action
    notes: str = ""


TEST_CASES: list[TestCase] = [
    # ==================== 1. 明确项目查优惠 ====================
    TestCase(
        case_id="SC-001",
        title="明确项目：换机油查优惠",
        description="用户明确指定项目，直接查优惠",
        user_input="换机油有优惠吗？",
        expected_behavior="识别项目为'换机油' → 调 search_coupon(project_ids=['xxx']) → 返回该项目的商户优惠和平台优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": ["oil_change"], "city": None, "semantic_query": None}}
        ],
        expected_output_type="spec",
        notes="优惠用 CouponCard spec 展示，必须包含金额、条件、有效期"
    ),

    TestCase(
        case_id="SC-002",
        title="明确项目+支付方式偏好",
        description="用户指定项目并提到支付偏好，semantic_query 包含偏好信息",
        user_input="换轮胎有优惠吗？最好是支付宝的。",
        expected_behavior="识别项目'换轮胎' + 支付偏好'支付宝' → search_coupon(project_ids=['轮胎'], semantic_query='支付宝') → 展示优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": ["tire_change"], "semantic_query": "支付宝支付"}}
        ],
        expected_output_type="spec",
        notes="semantic_query 要从对话回顾组装，不遗漏用户的偏好"
    ),

    # ==================== 2. 无项目查优惠 ====================
    TestCase(
        case_id="SC-003",
        title="无项目查优惠：引导确认",
        description="用户没说具体项目，Agent 应短问确认",
        user_input="有什么优惠活动吗？",
        expected_behavior="Agent 识别缺少项目信息 → 短问'您要做什么项目？保养、换轮胎、还是？' → 等待用户回答后再查",
        expected_tool_calls=[],
        expected_output_type="text",
        notes="不要直接调 search_coupon(project_ids=null)，必须先引导用户确认项目"
    ),

    TestCase(
        case_id="SC-004",
        title="无项目查平台优惠（城市维度）",
        description="用户查热门优惠，指定城市",
        user_input="北京现在有什么优惠活动？",
        expected_behavior="city='北京' → search_coupon(city='北京', sort_by='default', top_k=10) → 返回该城市热门优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": None, "city": "北京", "sort_by": "default", "top_k": 10}}
        ],
        expected_output_type="spec",
        notes="可在无项目的情况下按城市查，作为保底方案"
    ),

    # ==================== 3. Semantic_query 多轮累积 ====================
    TestCase(
        case_id="SC-005",
        title="多轮对话：偏好累积轮 1",
        description="轮 1 用户说要换机油",
        user_input="帮我看看换机油的优惠。",
        expected_behavior="project_ids=['oil_change'] → semantic_query=null（暂无偏好）→ search_coupon → 返回优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": ["oil_change"]}}
        ],
        expected_output_type="spec",
        notes="session_state 记录 project_ids"
    ),

    TestCase(
        case_id="SC-006",
        title="多轮对话：偏好累积轮 2",
        description="轮 2 用户添加新偏好'支付宝的'，semantic_query 应包含此前提到的所有偏好",
        user_input="要支付宝的活动。",
        expected_behavior="识别轮 1 project_ids + 轮 2 偏好'支付宝' → search_coupon(project_ids=['oil_change'], semantic_query='支付宝支付') → 返回更新的优惠列表",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": ["oil_change"], "semantic_query": "支付宝支付"}}
        ],
        expected_output_type="spec",
        notes="semantic_query 多轮累积，不遗漏任何偏好"
    ),

    TestCase(
        case_id="SC-007",
        title="多轮对话：偏好累积轮 3",
        description="轮 3 用户再加条件'送洗车的'，semantic_query 继续累积",
        user_input="最好还送洗车。",
        expected_behavior="semantic_query='支付宝支付 + 送洗车' → search_coupon → 返回满足条件的优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": ["oil_change"], "semantic_query": "支付宝支付的、送洗车的"}}
        ],
        expected_output_type="spec",
        notes="多轮偏好完整组装，不遗漏"
    ),

    # ==================== 4. 没查到商户优惠 ====================
    TestCase(
        case_id="SC-008",
        title="无商户优惠：介绍平台九折",
        description="search_coupon 返回空的 shopActivities，Agent 应介绍平台九折作为补充",
        user_input="变速箱油有什么优惠吗？",
        expected_behavior="search_coupon 返回空 shopActivities → Agent 说'虽然没有专门活动，但通过话痨预订可以九折，预估省 XX 元' → 引导到预订流程",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": ["transmission_fluid"]}}
        ],
        expected_output_type="text",
        notes="使用 saving-methods skill 介绍四种省钱方式，只讲概要"
    ),

    # ==================== 5. Apply_coupon 流程 ====================
    TestCase(
        case_id="SC-009",
        title="用户选择优惠并确认时间",
        description="优惠展示后，用户选择某个优惠并提供到店时间",
        user_input="我要这个机油 8 折的，下午 2 点去。",
        expected_behavior="识别用户选的活动 ID + 时间'14:00' → apply_coupon(activity_id='xxx', shop_id='xxx', visit_time='14:00') → 返回联系单编号",
        expected_tool_calls=[
            {"tool": "apply_coupon", "params": {"activity_id": "ACT123", "shop_id": "1001", "visit_time": "14:00"}}
        ],
        expected_output_type="action",
        notes="visit_time 格式 HH:MM，来自对话提取"
    ),

    TestCase(
        case_id="SC-010",
        title="用户选优惠但未提供时间，Agent 确认",
        description="用户选优惠但没说到店时间，Agent 应主动确认",
        user_input="就这个活动，帮我申请。",
        expected_behavior="Agent 识别缺少到店时间 → 短问'您大概什么时间到店？' → 等待用户回答后调 apply_coupon",
        expected_tool_calls=[],
        expected_output_type="text",
        notes="确认时间后再调 apply_coupon，不能缺少此参数"
    ),

    # ==================== 6. 城市筛选 ====================
    TestCase(
        case_id="SC-011",
        title="按城市查优惠（多城市场景）",
        description="用户指定城市范围查优惠",
        user_input="上海做保养有什么优惠吗？",
        expected_behavior="识别 city='上海' + project='保养' → search_coupon(city='上海', project_ids=['maintenance']) → 返回该城市的优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"city": "上海", "project_ids": ["maintenance"]}}
        ],
        expected_output_type="spec",
        notes="city 参数有效处理多城市场景"
    ),

    # ==================== 7. 排序需求 ====================
    TestCase(
        case_id="SC-012",
        title="排序：按优惠金额（最便宜优先）",
        description="用户明确要'最便宜的优惠'，应按 discount_amount 排序",
        user_input="帮我找最便宜的保养优惠。",
        expected_behavior="识别排序偏好'最便宜' → search_coupon(project_ids=['maintenance'], sort_by='discount_amount') → 返回按金额倒序的优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"project_ids": ["maintenance"], "sort_by": "discount_amount"}}
        ],
        expected_output_type="spec",
        notes="sort_by='discount_amount' 表示按金额排序"
    ),

    TestCase(
        case_id="SC-013",
        title="排序：即将过期优先",
        description="用户想要'快要过期的活动'，应按 validity_end 排序",
        user_input="有没有快要过期的优惠？我想趁快完了赶紧用。",
        expected_behavior="识别排序偏好'快要过期' → search_coupon(sort_by='validity_end') → 返回按过期日期升序的优惠",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"sort_by": "validity_end"}}
        ],
        expected_output_type="spec",
        notes="sort_by='validity_end' 表示过期优先"
    ),

    # ==================== 8. 模糊/多意图查询 ====================
    TestCase(
        case_id="SC-014",
        title="模糊查询：'有没有什么好的活动'",
        description="用户很模糊，不指定项目或城市，Agent 应引导",
        user_input="有没有什么好的活动？",
        expected_behavior="识别信息不足 → 短问'您想查哪个城市的优惠，或者要做什么项目的？' → 等待用户明确",
        expected_tool_calls=[],
        expected_output_type="text",
        notes="模糊查询需要引导，不能直接调 search_coupon()"
    ),

    # ==================== 9. 预订意图转换 ====================
    TestCase(
        case_id="SC-015",
        title="用户想预订（不只是申领优惠）",
        description="用户在查优惠后表示想预订，应引导到预订流程而不仅仅申领",
        user_input="这个优惠不错，帮我订一下吧。",
        expected_behavior="Agent 识别预订意图 → 说'我帮你安排预订' → 下一轮自然进入预订流程（可能调 booking skill 或相关工具）",
        expected_tool_calls=[],
        expected_output_type="text",
        notes="预订是更大的流程，需要转换场景，不只是 apply_coupon"
    ),

    # ==================== 10. 位置相关查询 ====================
    TestCase(
        case_id="SC-016",
        title="位置相关：'附近的优惠'",
        description="用户提到'附近'，应尝试用位置信息筛选（如果 session 有位置数据）",
        user_input="我现在在北京朝阳区，附近有什么优惠吗？",
        expected_behavior="提取城市'北京' + 识别位置需求 → search_coupon(city='北京') → 返回该地区优惠。若有精确地理位置可用，可传给后端做距离筛选",
        expected_tool_calls=[
            {"tool": "search_coupon", "params": {"city": "北京"}}
        ],
        expected_output_type="spec",
        notes="位置提取依赖 session 状态或 GPS，当前以城市作为粗粒度位置"
    ),
]


def print_test_cases() -> None:
    """打印测试用例概览"""
    print("=" * 100)
    print("searchcoupons 场景测试用例设计（16 个用例）")
    print("=" * 100)

    categories: dict[str, list[TestCase]] = {
        "明确项目查优惠": [],
        "无项目查优惠": [],
        "Semantic_query 多轮累积": [],
        "没查到商户优惠": [],
        "Apply_coupon 流程": [],
        "城市筛选": [],
        "排序需求": [],
        "模糊查询": [],
        "预订意图转换": [],
        "位置相关": [],
    }

    # 分类
    for tc in TEST_CASES:
        if tc.case_id in ["SC-001", "SC-002"]:
            categories["明确项目查优惠"].append(tc)
        elif tc.case_id in ["SC-003", "SC-004"]:
            categories["无项目查优惠"].append(tc)
        elif tc.case_id in ["SC-005", "SC-006", "SC-007"]:
            categories["Semantic_query 多轮累积"].append(tc)
        elif tc.case_id in ["SC-008"]:
            categories["没查到商户优惠"].append(tc)
        elif tc.case_id in ["SC-009", "SC-010"]:
            categories["Apply_coupon 流程"].append(tc)
        elif tc.case_id in ["SC-011"]:
            categories["城市筛选"].append(tc)
        elif tc.case_id in ["SC-012", "SC-013"]:
            categories["排序需求"].append(tc)
        elif tc.case_id in ["SC-014"]:
            categories["模糊查询"].append(tc)
        elif tc.case_id in ["SC-015"]:
            categories["预订意图转换"].append(tc)
        elif tc.case_id in ["SC-016"]:
            categories["位置相关"].append(tc)

    for category, cases in categories.items():
        if cases:
            print(f"\n### {category} ({len(cases)} 个)")
            print("-" * 100)
            for tc in cases:
                print(f"  {tc.case_id}: {tc.title}")
                print(f"    输入：{tc.user_input}")
                print(f"    期望行为：{tc.expected_behavior}")
                print()


if __name__ == "__main__":
    print_test_cases()
