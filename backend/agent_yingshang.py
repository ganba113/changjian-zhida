# -*- coding: utf-8 -*-
"""
检护营商智能体 —— 食品安全领域行政处罚监督线索筛查（规则引擎）

职责：
1. 提供「映射表刻度」：每种处罚条款对应的法定罚款幅度（PENALTY_BASELINE）
2. 提供「停用/废止」清单：已废止规章、停用基准编码
3. 规则引擎：对一批「字段记录」跑 R0 + 规则一二三，输出两档线索
4. 字段提取 prompt（原始文书 → 16 字段，由 vLLM 执行）
5. 主体碰撞：按统一社会信用代码判定主体类型（小规模 / 一般企业 / 连锁）

单位约定：罚款、没收、法定幅度一律用「万元」；货值用「元」。
金额区间中的「5-6.5万」表示罚款 5 万元至 6.5 万元；「10-13倍」表示货值金额的 10 至 13 倍。
货值 1 万元是双轨分界：不足 1 万按固定金额档，1 万以上按倍数档。
"""

import json
import re
import io

# ============================================================================
# 一、映射表刻度（处罚条款 -> 法定罚款幅度）
#   key   ：规范化条款标识（法规_条款_款）
#   min   ：法定最低罚款（万元，固定金额档）
#   max   ：法定最高罚款（万元，固定金额档）
#   dual  ：是否货值双轨（True 表示货值>=1万走倍数档）
#   min_times / max_times ：倍数档的倍数范围（仅 dual=True 时有效）
#   progressive ：递进条款（先责令改正/警告，拒不改正才罚款）
# ============================================================================
PENALTY_BASELINE = {
    # ---- 中华人民共和国食品安全法（2025 修正）----
    "shianfa_122_1": {"law": "食品安全法", "article": "第一百二十二条第一款",
                      "min": 5.0, "max": 8.5, "dual": True, "min_times": 10, "max_times": 17},
    "shianfa_122_2": {"law": "食品安全法", "article": "第一百二十二条第二款",
                      "min": 5.0, "max": 8.5, "dual": False},
    "shianfa_123_1": {"law": "食品安全法", "article": "第一百二十三条第一款",
                      "min": 10.0, "max": 13.5, "dual": True, "min_times": 15, "max_times": 26},
    "shianfa_123_2": {"law": "食品安全法", "article": "第一百二十三条第二款",
                      "min": 10.0, "max": 17.0, "dual": False},
    "shianfa_124_1": {"law": "食品安全法", "article": "第一百二十四条第一款",
                      "min": 5.0, "max": 8.5, "dual": True, "min_times": 10, "max_times": 17},
    "shianfa_124_2": {"law": "食品安全法", "article": "第一百二十四条第二款",
                      "min": 5.0, "max": 8.5, "dual": True, "min_times": 10, "max_times": 17},
    "shianfa_125_1": {"law": "食品安全法", "article": "第一百二十五条第一款",
                      "min": 1.85, "max": 3.65, "dual": True, "min_times": 5, "max_times": 8.5},
    "shianfa_125_2": {"law": "食品安全法", "article": "第一百二十五条第二款",
                      "min": 0.0, "max": 0.14, "dual": False},
    "shianfa_126_1": {"law": "食品安全法", "article": "第一百二十六条第一款",
                      "min": 1.85, "max": 3.65, "dual": False, "progressive": True},
    "shianfa_126_4": {"law": "食品安全法", "article": "第一百二十六条第四款",
                      "min": 1.85, "max": 3.65, "dual": False, "progressive": True},
    "shianfa_128":   {"law": "食品安全法", "article": "第一百二十八条",
                      "min": 10.0, "max": 38.0, "dual": False},
    "shianfa_130_1": {"law": "食品安全法", "article": "第一百三十条第一款",
                      "min": 5.0, "max": 15.5, "dual": False},
    "shianfa_130_2": {"law": "食品安全法", "article": "第一百三十条第二款",
                      "min": 5.0, "max": 15.5, "dual": False},
    "shianfa_131_1": {"law": "食品安全法", "article": "第一百三十一条第一款",
                      "min": 5.0, "max": 15.5, "dual": False},
    "shianfa_132":   {"law": "食品安全法", "article": "第一百三十二条",
                      "min": 1.0, "max": 3.8, "dual": False, "progressive": True},
    "shianfa_133_1": {"law": "食品安全法", "article": "第一百三十三条第一款",
                      "min": 0.2, "max": 3.56, "dual": False},
    "shianfa_140_5": {"law": "食品安全法", "article": "第一百四十条第五款",
                      "min": 2.0, "max": 3.8, "dual": False},

    # ---- 北京市小规模食品生产经营管理规定 ----
    "xiaoguimo_22_1": {"law": "北京市小规模食品生产经营管理规定", "article": "第二十二条第一款",
                       "min": 1.85, "max": 3.65, "dual": False},
    "xiaoguimo_22_2": {"law": "北京市小规模食品生产经营管理规定", "article": "第二十二条第二款",
                       "min": 0.29, "max": 0.29, "dual": False},
    "xiaoguimo_23":   {"law": "北京市小规模食品生产经营管理规定", "article": "第二十三条",
                       "min": 1.85, "max": 3.65, "dual": False},
    "xiaoguimo_24_1": {"law": "北京市小规模食品生产经营管理规定", "article": "第二十四条第一款",
                       "min": 1.85, "max": 3.65, "dual": False},
    "xiaoguimo_24_2": {"law": "北京市小规模食品生产经营管理规定", "article": "第二十四条第二款",
                       "min": 0.2, "max": 0.44, "dual": False},
    "xiaoguimo_25":   {"law": "北京市小规模食品生产经营管理规定", "article": "第二十五条",
                       "min": 10.0, "max": 13.5, "dual": True, "min_times": 15, "max_times": 26},
    "xiaoguimo_26":   {"law": "北京市小规模食品生产经营管理规定", "article": "第二十六条",
                       "min": 1.85, "max": 3.65, "dual": False},
    "xiaoguimo_27":   {"law": "北京市小规模食品生产经营管理规定", "article": "第二十七条",
                       "min": 0.2, "max": 0.76, "dual": False},
    "xiaoguimo_28":   {"law": "北京市小规模食品生产经营管理规定", "article": "第二十八条",
                       "min": 0.1, "max": 0.38, "dual": False, "progressive": True},
    "xiaoguimo_29":   {"law": "北京市小规模食品生产经营管理规定", "article": "第二十九条",
                       "min": 0.05, "max": 0.085, "dual": False, "progressive": True},

    # ---- 中华人民共和国食品安全法实施条例（2019 修订）----
    "shishitiao_72":  {"law": "食品安全法实施条例", "article": "第七十二条",
                       "min": 1.0, "max": 3.8, "dual": False, "progressive": True},
    "shishitiao_74":  {"law": "食品安全法实施条例", "article": "第七十四条",
                       "min": 1.0, "max": 3.8, "dual": True, "min_times": 5, "max_times": 8.5},
    "shishitiao_75_1": {"law": "食品安全法实施条例", "article": "第七十五条第一款",
                        "min": 0.0, "max": 0.0, "dual": False},
    "shishitiao_80":  {"law": "食品安全法实施条例", "article": "第八十条",
                       "min": 10.0, "max": 85.0, "dual": False},

    # ---- 网络餐饮服务食品安全监督管理办法（旧，2026-06-01 废止）----
    # 递进结构：责令改正+警告 -> 拒不改正分档罚款（5000-12500元 -> 12500-22500元）
    "wangcan_28": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第二十八条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_29": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第二十九条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_30": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_31_2": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十一条第二款",
                     "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_32": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十二条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_34": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十四条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_36": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十六条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_37": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十七条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_38": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十八条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_39_4": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第三十九条第（四）项",
                     "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "wangcan_40": {"law": "网络餐饮服务食品安全监督管理办法", "article": "第四十条",
                   "min": 0.5, "max": 2.25, "dual": False, "progressive": True},

    # ---- 网络食品安全违法行为查处办法（2025 修订）----
    "chachu_29": {"law": "网络食品安全违法行为查处办法", "article": "第二十九条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_30": {"law": "网络食品安全违法行为查处办法", "article": "第三十条",
                  "min": 3.0, "max": 3.0, "dual": False, "progressive": True},
    "chachu_31": {"law": "网络食品安全违法行为查处办法", "article": "第三十一条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_33": {"law": "网络食品安全违法行为查处办法", "article": "第三十三条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_34": {"law": "网络食品安全违法行为查处办法", "article": "第三十四条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_35": {"law": "网络食品安全违法行为查处办法", "article": "第三十五条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_39": {"law": "网络食品安全违法行为查处办法", "article": "第三十九条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_40": {"law": "网络食品安全违法行为查处办法", "article": "第四十条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_41": {"law": "网络食品安全违法行为查处办法", "article": "第四十一条",
                  "min": 0.5, "max": 2.25, "dual": False, "progressive": True},
    "chachu_41_2": {"law": "网络食品安全违法行为查处办法", "article": "第四十一条第二款",
                    "min": 3.0, "max": 3.0, "dual": False},
    "chachu_43": {"law": "网络食品安全违法行为查处办法", "article": "第四十三条",
                  "min": 1.0, "max": 1.6, "dual": False},
}

# ============================================================================
# 二、停用 / 废止清单（规则三机制八 + R0.2 / R0.3 专用）
# ============================================================================
# 已废止规章（引用即命中 R0.2「失效依据直查」）
ABOLISHED_REGULATIONS = [
    "食品经营许可管理办法",  # 2023-12-01 已废止
]

# 2026-06-01 起废止的规章（仅对 2026-06-01 后处罚的案件命中 R0.3）
ABOLISHED_AFTER_20260601 = [
    "网络餐饮服务食品安全监督管理办法",
]

# 2024-12-06 公告停用的基准条目编码前缀（食用农产品相关，映射表第六节）
STOPPED_CODE_PREFIXES = [
    "C38804",  # 第9项 食用农产品农残兽残
    "C38744",  # 第20项
    "C38819",  # 第23项
    "C35432",  # 第37项
    "C35372",  # 第38项
    "C38912",  # 第44项
    "C38913",  # 第45项
]

# 递进条款标识集合（先责令改正/警告，拒不改正才罚款）
PROGRESSIVE_KEYS = {
    k for k, v in PENALTY_BASELINE.items() if v.get("progressive")
}

# ============================================================================
# 三、字段定义（与「字段提取表」16 列对齐，字段提取的标准输出结构）
# ============================================================================
FIELD_SPEC = {
    "doc_no": "文号",
    "party": "当事人",
    "credit_code": "统一社会信用代码",
    "subject_type": "主体类别",
    "source_pool": "检索来源池（食安法/小规模/实施条例/查处办法/网络餐饮/其他）",
    "main_article": "主处罚条款",
    "fine": "罚款金额（万元）",
    "confiscate": "没收金额（万元）",
    "goods_value": "货值金额（元）",
    "punish_date": "处罚决定日期",
    "has_full_text": "是否含决定书全文（1/0）",
    "order_correct": "责令改正（1/0）",
    "warning": "警告（1/0）",
    "refuse_correct": "拒不改正（1/0）",
    "mitigate": "减轻表述（1/0）",
    "baseline_code": "基准编码引用",
}

# 缺失值四态（E0 约定）
MISSING_NONE = "无"        # 文书明确没有该事项
MISSING_UNRECORDED = "未记载"  # 本应写明但文书没写（本身可能是指标）
MISSING_TBD = "待核"        # 有相关段落但机器没提出来


# ============================================================================
# 四、工具函数
# ============================================================================
_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9,
}


def _cn_to_int(s: str) -> int:
    """中文数字转整数（支持到几百），如「一百二十四」->124、「二十七」->27。"""
    if not s:
        return 0
    s = s.replace("第", "").replace("条", "").replace("款", "").replace("项", "")
    total = 0
    section = 0
    for ch in s:
        if ch in _CN_DIGIT:
            section = _CN_DIGIT[ch]
        elif ch == "十":
            total += (section if section else 1) * 10
            section = 0
        elif ch == "百":
            total += (section if section else 1) * 100
            section = 0
    return total + section


def _to_float(v, default=None):
    """宽松转 float；处理「0.05」「800元」「0.08万」「未记载」「无」等。"""
    if v is None:
        return default
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("，", "").replace(",", "")
    if not s or s in ("无", "未记载", "待核", "——", "-", "/"):
        return default
    m = re.search(r"(-?\d+(?:\.\d+)?)", s)
    if not m:
        return default
    val = float(m.group(1))
    if "元" in s and "万" not in s:
        val = val / 10000.0  # 元 -> 万元
    return val


_POOL_MAP = {
    "食安法": "shianfa",
    "小规模": "xiaoguimo",
    "实施条例": "shishitiao",
    "查处办法": "chachu",
    "网络餐饮": "wangcan",
}


def match_article_key(source_pool: str, main_article: str):
    """把「检索来源池 + 主处罚条款」映射到 PENALTY_BASELINE 的 key；匹配不到返回 None。"""
    pool = (source_pool or "").strip()
    art = (main_article or "").strip()
    if not art or art in ("其他", "未记载", "待核", "无"):
        return None
    # 优先从 main_article 里识别法规
    prefix = None
    if "小规模" in art:
        prefix = "xiaoguimo"
    elif "食安法" in art or "食品安全法" in art:
        prefix = "shianfa"
    elif "实施条例" in art:
        prefix = "shishitiao"
    elif "查处办法" in art:
        prefix = "chachu"
    elif "网络餐饮" in art:
        prefix = "wangcan"
    else:
        prefix = _POOL_MAP.get(pool)
    if not prefix:
        return None
    # 提取条款号（阿拉伯数字优先，其次中文数字，兼容「124条」「第一百二十四条」「小规模二十七」）
    m = re.search(r"(\d+)\s*条", art)
    if m:
        num = int(m.group(1))
    else:
        m = re.search(r"第([零一二两三四五六七八九十百]+)条", art)
        if m:
            num = _cn_to_int(m.group(1))
        else:
            m = re.search(r"([零一二两三四五六七八九十百]+)", art)
            num = _cn_to_int(m.group(1)) if m else None
    if num is None:
        return None
    # 款 / 项
    section = 1
    if "第二款" in art or "第2款" in art:
        section = 2
    elif "第四款" in art or "第4款" in art:
        section = 4
    elif "第（四）项" in art or "（四）项" in art:
        section = 4
    key = f"{prefix}_{num}"
    if section != 1:
        key = f"{key}_{section}"
    if key not in PENALTY_BASELINE:
        # 尝试退回第 1 款
        key1 = f"{prefix}_{num}"
        if key1 in PENALTY_BASELINE:
            return key1
        return None
    return key


def _subject_type(credit_code: str, party_name: str, collision_lookup=None) -> str:
    """判定主体类型：连锁 / 一般企业 / 小规模 / 个体户 / 未知。"""
    name = (party_name or "").strip()
    if not name:
        return "未知"
    if "连锁" in name:
        return "连锁"
    # 碰撞表命中 → 小规模主体（小作坊/小餐饮/小食杂店）
    if collision_lookup and credit_code:
        try:
            hit = collision_lookup(credit_code)
        except Exception:
            hit = None
        if hit:
            return "小规模"
    if any(k in name for k in ("有限公司", "有限责任公司", "股份有限公司", "公司")):
        return "一般企业"
    if "个体工商户" in name or "个体" in name:
        return "个体户"
    # 名称是「XX店」「XX中心」「XX站」等 → 疑似小规模
    if any(k in name for k in ("店", "中心", "站", "馆", "铺", "摊")):
        return "个体户"
    return "未知"


# ============================================================================
# 五、规则引擎
# ============================================================================
def screen_records(records, collision_lookup=None):
    """对一批字段记录跑 R0 + 规则一二三，输出两档线索清单。

    records: list[dict]，每个 dict 字段名见 FIELD_SPEC（doc_no/party/.../baseline_code）。
    collision_lookup: 可选 callable(credit_code)->bool，命中表示该主体在小规模许可/备案表中。
    返回 list[dict]，每个元素 = 一条线索（一个文号可能聚合多条命中规则）。
    """
    parsed = []
    for r in records:
        rec = dict(r)
        fine = _to_float(rec.get("fine"))
        goods = _to_float(rec.get("goods_value"))
        conf = _to_float(rec.get("confiscate"))
        rec["_fine"] = fine
        rec["_goods"] = goods
        rec["_conf"] = conf
        rec["_key"] = match_article_key(rec.get("source_pool"), rec.get("main_article"))
        rec["_has_full"] = str(rec.get("has_full_text", "")).strip() in ("1", "true", "是", "True")
        rec["_subject"] = _subject_type(
            rec.get("credit_code"), rec.get("party"), collision_lookup
        )
        parsed.append(rec)

    # 分组：按处罚条款 key + 主体类型（用于规则一内部比对）
    groups = {}
    for rec in parsed:
        if rec["_key"] and rec["_fine"] is not None:
            groups.setdefault((rec["_key"], rec["_subject"]), []).append(rec)
    group_median = {}
    for gk, lst in groups.items():
        fines = sorted(x["_fine"] for x in lst)
        n = len(fines)
        if n == 0:
            continue
        group_median[gk] = fines[n // 2] if n % 2 else (fines[n // 2 - 1] + fines[n // 2]) / 2.0

    hints = []
    for rec in parsed:
        hits = _screen_one(rec, group_median, collision_lookup)
        if hits:
            level = "明显异常" if any(h["level"] == "明显异常" for h in hits) else "疑点线索"
            hints.append({
                "doc_no": rec.get("doc_no", ""),
                "party": rec.get("party", ""),
                "credit_code": rec.get("credit_code", ""),
                "source_pool": rec.get("source_pool", ""),
                "main_article": rec.get("main_article", ""),
                "fine": rec.get("fine"),
                "goods_value": rec.get("goods_value"),
                "level": level,
                "rules": [{"code": h["code"], "name": h["name"], "detail": h["detail"]} for h in hits],
            })
    return hints


def _hit(code, name, detail, level="疑点线索"):
    return {"code": code, "name": name, "detail": detail, "level": level}


def _screen_one(rec, group_median, collision_lookup):
    """单条记录跑全部规则，返回命中列表。"""
    hits = []
    fine = rec["_fine"]
    goods = rec["_goods"]
    conf = rec["_conf"]
    key = rec["_key"]
    base = PENALTY_BASELINE.get(key) if key else None
    article_text = (rec.get("main_article") or "") + " " + (rec.get("source_pool") or "")
    code_ref = (rec.get("baseline_code") or "").strip()
    subject = rec["_subject"]
    name = rec.get("party", "")
    has_full = rec["_has_full"]
    punish_date = str(rec.get("punish_date") or "")

    # ---- R0.2 失效依据直查 ----
    for reg in ABOLISHED_REGULATIONS:
        if reg in article_text or reg in code_ref:
            hits.append(_hit("R0.2", "失效依据直查",
                             f"处罚依据引用已废止规章《{reg}》", "明显异常"))

    # ---- R0.3 网络餐饮切换（2026-06-01 后引用旧办法）----
    if punish_date >= "2026-06-01":
        for reg in ABOLISHED_AFTER_20260601:
            if reg in article_text:
                hits.append(_hit("R0.3", "网络餐饮切换",
                                 f"2026-06-01 后仍引用已废止的《{reg}》", "明显异常"))

    # ---- 机制八 引用失效依据（停用编码）----
    if code_ref:
        for pre in STOPPED_CODE_PREFIXES:
            if code_ref.upper().startswith(pre):
                hits.append(_hit("机制八", "引用失效依据",
                                 f"引用 2024-12-06 公告停用的基准编码 {code_ref}", "明显异常"))

    # ---- 货值金额未记载（E0 程序瑕疵线索）----
    if rec.get("goods_value") in ("未记载", "待核") or goods is None:
        hits.append(_hit("E0", "货值金额未记载",
                         "货值金额未记载，无法对应裁量档次，需调全文核实"))

    # 以下规则需要命中「处罚条款 -> 幅度」
    if base is None:
        return hits

    legal_min = base["min"]
    legal_max = base["max"]
    law_name = base["law"]
    art_name = base["article"]

    # ---- 规则一：同组罚款悬殊（R1.1）----
    if fine is not None and fine > 0:
        median = group_median.get((key, subject))
        if median and median > 0 and abs(fine - median) > 0:
            if legal_min <= 0.5:  # 小额组：绝对差>=500元 且 偏离中位数50%以上
                if abs(fine - median) >= 0.05 and abs(fine - median) / median >= 0.5:
                    hits.append(_hit("R1.1", "同组罚款悬殊",
                                     f"同组（{law_name}{art_name}/{subject}）罚款中位数 {median} 万，"
                                     f"本案 {fine} 万偏离 {abs(fine - median) / median * 100:.0f}%"))
            else:  # 大额组：偏离中位数 ±50% 以上
                if abs(fine - median) / median >= 0.5:
                    hits.append(_hit("R1.1", "同组罚款悬殊",
                                     f"同组（{law_name}{art_name}/{subject}）罚款中位数 {median} 万，"
                                     f"本案 {fine} 万偏离 {abs(fine - median) / median * 100:.0f}%"))

    # ---- 规则二（幅度审查）----
    if fine is not None:
        # R2.1 顶格
        if fine >= legal_max - 1e-9 and legal_max > 0:
            hits.append(_hit("R2.1", "顶格处罚",
                             f"罚款 {fine} 万达到法定上限 {legal_max} 万，公示未见从重情节说明"))
        # R2.2 接近顶格
        elif legal_max > 0 and fine >= legal_max * 0.9:
            hits.append(_hit("R2.2", "接近顶格",
                             f"罚款 {fine} 万≥法定上限 {legal_max} 万的 90%"))
        # R2.3 莫名减轻（主规则）
        if legal_min > 0 and fine < legal_min:
            has_mitigate = str(rec.get("mitigate", "")).strip() in ("1", "true", "是", "True")
            if not has_mitigate:
                hits.append(_hit("R2.3", "莫名减轻",
                                 f"罚款 {fine} 万低于法定下限 {legal_min} 万（{law_name}{art_name}），"
                                 f"公示信息未见减轻理由，需调全文核实减轻依据"))
            else:
                # 有减轻表述 -> 进入减轻幅度比对（R1.4）
                ratio = fine / legal_min if legal_min else 0
                hits.append(_hit("R1.4", "减轻幅度比对",
                                 f"减轻幅度 {ratio * 100:.1f}%（实罚 {fine} 万 ÷ 法定下限 {legal_min} 万），"
                                 f"显著低于法定下限，需比对同案减轻幅度"))

    # ---- 机制二 跳步骤罚款（递进条款）----
    if key in PROGRESSIVE_KEYS and fine is not None and fine > 0:
        refuse = str(rec.get("refuse_correct", "")).strip()
        order = str(rec.get("order_correct", "")).strip()
        if refuse not in ("1", "true", "是", "True") and order not in ("1", "true", "是", "True"):
            hits.append(_hit("机制二", "跳步骤罚款",
                             f"处罚依据为递进条款（{law_name}{art_name}），应责令改正/警告、"
                             f"拒不改正才罚款，却直接罚款 {fine} 万，需调全文核实「拒不改正」认定"))

    # ---- 机制三 漏掉并罚（应没收并处却只罚款，且没收「未记载」）----
    if str(rec.get("confiscate", "")).strip() == "未记载" and fine is not None and fine > 0:
        hits.append(_hit("机制三", "漏掉并罚",
                         "处罚类别仅罚款、没收违法所得「未记载」，需核实是否属应并处没收的情形"))

    # ---- 机制五 小店按大法重罚 ----
    if subject in ("小规模", "个体户") and key.startswith("shianfa_") and key in (
        "shianfa_122_1", "shianfa_124_1"
    ):
        hits.append(_hit("机制五", "小店按大法重罚",
                         f"主体疑似小规模经营者（{subject}），却按《食品安全法》"
                         f"{art_name} 处罚，应优先适用《北京市小规模食品生产经营管理规定》"))

    # ---- 机制六 非小店按小法轻罚 ----
    if subject in ("一般企业", "连锁") and key.startswith("xiaoguimo_"):
        hits.append(_hit("机制六", "非小店按小法轻罚",
                         f"主体为{subject}（小规模规定明确排除连锁），却按《北京市小规模"
                         f"食品生产经营管理规定》轻罚，需碰撞许可证数据核实主体资格"))

    return hits


# ============================================================================
# 六、字段提取（原始文书 -> 16 字段，由 vLLM 执行）
# ============================================================================
EXTRACT_SYSTEM = (
    "你是食品安全行政处罚文书字段提取助手。请严格从给定文书/公示信息中提取字段，"
    "不要臆测，没有的填「未记载」或「无」。罚款、没收统一换算成「万元」数值，"
    "货值统一用「元」数值。只输出 JSON，不要输出任何解释文字。"
)

EXTRACT_FIELDS_JSON = """{
  "doc_no": "行政处罚决定书文号",
  "party": "当事人名称",
  "credit_code": "统一社会信用代码(无则空字符串)",
  "subject_type": "行政相对人类别(如个体工商户/有限责任公司)",
  "source_pool": "检索来源池, 取: 食安法/小规模/实施条例/查处办法/网络餐饮/其他",
  "main_article": "主处罚条款(如'小规模二十七'、'食安法124条'、'其他')",
  "fine": "罚款金额(万元数值, 无则0)",
  "confiscate": "没收金额(万元数值, 无则'无')",
  "goods_value": "货值金额(元数值, 未记载则'未记载')",
  "punish_date": "处罚决定日期(YYYY-MM-DD)",
  "has_full_text": "是否含决定书全文(1/0)",
  "order_correct": "是否责令改正(1/0)",
  "warning": "是否警告(1/0)",
  "refuse_correct": "是否拒不改正(1/0)",
  "mitigate": "是否有减轻/从轻表述(1/0)",
  "baseline_code": "基准编码引用(如C35259A010, 无则空字符串)"
}"""


def build_extract_prompt(text: str) -> str:
    return (
        "请从以下行政处罚文书/公示信息中提取字段，输出严格 JSON：\n"
        "字段说明：\n" + EXTRACT_FIELDS_JSON + "\n\n"
        "文书内容：\n" + text[:8000]
    )


def parse_json_lenient(text: str):
    """宽松解析 LLM 返回的 JSON（容忍 markdown 代码块、前后杂文）。"""
    if not text:
        return None
    s = text.strip()
    # 去掉 markdown 代码块包裹
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.S)
    if m:
        s = m.group(1)
    else:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            s = s[start : end + 1]
    try:
        return json.loads(s)
    except Exception:
        return None


# ============================================================================
# 七、主体碰撞（市监局许可 / 备案表）
# ============================================================================
COLLISION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ys_collision (
    credit_code TEXT PRIMARY KEY,
    name        TEXT,
    source      TEXT,
    detail      TEXT
)
"""


def _read_xlsx_rows(data: bytes):
    """解析 xlsx，返回 (header_list, data_rows)。用单元格列字母定位列，空单元格填空串。"""
    import zipfile
    from xml.etree import ElementTree as ET

    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return [], []

    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))

    def cellval(c):
        t = c.get("t")
        v = c.find(NS + "v")
        if v is None:
            return ""
        val = v.text or ""
        if t == "s":
            try:
                return shared[int(val)]
            except Exception:
                return ""
        return val

    def col_idx(ref):
        letters = re.sub(r"[^A-Za-z]", "", ref or "")
        idx = 0
        for ch in letters.upper():
            idx = idx * 26 + (ord(ch) - ord("A") + 1)
        return idx - 1

    def rowvals(r):
        cells = {}
        for c in r.findall(NS + "c"):
            cells[col_idx(c.get("r"))] = cellval(c)
        if not cells:
            return []
        return [cells.get(i, "") for i in range(max(cells) + 1)]

    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = sheet.findall(NS + "sheetData")[0].findall(NS + "row")
    if not rows:
        return [], []
    header = rowvals(rows[0])
    data = [rowvals(r) for r in rows[1:]]
    return header, data


def parse_collision_xlsx(data: bytes, source_label: str):
    """解析市监局许可/备案 xlsx，返回 [(credit_code, name, source, detail), ...]。"""
    header, rows = _read_xlsx_rows(data)
    if not header:
        return []

    def colidx(*names):
        for i, h in enumerate(header):
            for nm in names:
                if nm in (h or ""):
                    return i
        return -1

    ci_code = colidx("统一社会信用代码")
    ci_name = colidx("经营者名称", "行政相对人名称", "当事人")
    ci_detail = colidx("经营项目", "经营场所")
    if ci_code < 0:
        return []
    result = []
    for vals in rows:
        code = (vals[ci_code] if ci_code < len(vals) else "").strip()
        if not code:
            continue
        nm = vals[ci_name].strip() if (ci_name >= 0 and ci_name < len(vals)) else ""
        detail = vals[ci_detail].strip() if (ci_detail >= 0 and ci_detail < len(vals)) else ""
        result.append((code, nm, source_label, detail))
    return result


# 字段表列名（中文表头）-> FIELD_SPEC 字段 key（模糊匹配）
_FIELD_COLUMN_MAP = {
    "文号": "doc_no", "当事人": "party", "统一社会信用代码": "credit_code",
    "主体类别": "subject_type", "检索来源池": "source_pool", "主处罚条款": "main_article",
    "罚款": "fine", "没收": "confiscate", "货值": "goods_value",
    "处罚决定日期": "punish_date", "含决定书全文": "has_full_text", "责令改正": "order_correct",
    "警告": "warning", "拒不改正": "refuse_correct", "减轻表述": "mitigate",
    "基准编码引用": "baseline_code",
}


def parse_fields_xlsx(data: bytes):
    """解析「字段提取表」xlsx，返回 list[dict]（FIELD_SPEC 字段）。"""
    header, rows = _read_xlsx_rows(data)
    if not header:
        return []
    col_map = {}
    for i, h in enumerate(header):
        for key, field in _FIELD_COLUMN_MAP.items():
            if key in (h or "") and field not in col_map:
                col_map[field] = i
    if "doc_no" not in col_map:
        return []
    result = []
    for vals in rows:
        rec = {}
        for field, i in col_map.items():
            rec[field] = vals[i].strip() if i < len(vals) else ""
        if rec.get("doc_no"):
            result.append(rec)
    return result

