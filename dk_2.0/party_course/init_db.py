from werkzeug.security import generate_password_hash

from app import create_app
from models import NotificationTemplate, User, db


DEFAULT_TEMPLATES = [
    {
        "title": "报名通知（副书记群）",
        "category": "报名",
        "content": "各位副书记：第{{期数}}期入党积极分子党课培训和第{{期数}}期预备党员党课培训即将开展，请各位提醒相应阶段的同学加入对应的党课群，后续将在群里通知党课时间、地点及考试通知。\n易班课群邀请码：积极分子培训班 {{积极分子易班码}} / 预备党员培训班 {{预备党员易班码}}\nQQ群号：积极分子培训班 {{积极分子QQ群}} / 预备党员培训班 {{预备党员QQ群}}\n党课报名名单收集链接：积极分子 {{积极分子报名链接}} / 预备党员 {{预备党员报名链接}}\n请提醒相关同学于今晚10点前填好信息收集表@全体成员",
    },
    {
        "title": "上课通知",
        "category": "上课",
        "content": "@全体成员 党课暂定{{上课日期}}下午{{上课时间}}开班，争取{{结束时间}}结束，地点{{上课地点}}，第一次党课请尽量参加，请各位上课的同学佩戴党徽或团徽，会有签到，上党课要记笔记，具体分组情况见下方，每组第一位同学是小组长，小组长请加群（群号：{{小组长群号}}）",
    },
    {
        "title": "笔记提交通知",
        "category": "上课",
        "content": "@全体成员 {{提交日期}}前请各组员提交以下材料（全部写到笔记本上）（未提交取消结业资格）：\n1. 党课笔记（共{{课次数}}次，一次课一次笔记，每次500字以上）\n2. 个人心得至少1500字（可根据党课感悟及自学材料撰写）\n3. 小组讨论纪要（每个人都需提交，不少于500字）",
    },
    {
        "title": "考试通知",
        "category": "考试",
        "content": "@全体成员 易班考试题库练习将于{{开放日期}}正式开放，练习至{{截止日期}}。拟定于{{考试日期}}下午{{考试时间}}在线下进行结业考试，仅此一次，没有补考！请大家在考试当天准备好志愿汇的志愿时长证明及身份证。",
    },
    {
        "title": "成绩公示通知",
        "category": "成绩",
        "content": "@全体成员 本届党课成绩已公示，通过名单及证书编号见：{{公示链接}} 证书将由小组长统一领取后分发，请关注小组长通知。",
    },
]


def init_database() -> None:
    app = create_app()

    with app.app_context():
        db.create_all()

        admin = User.query.filter_by(username="admin").first()
        if admin is None:
            admin = User(
                username="admin",
                password_hash=generate_password_hash("admin123"),
                role="admin",
                real_name="系统管理员",
            )
            db.session.add(admin)
            db.session.commit()
            print("Default admin created: username=admin, password=admin123")
        else:
            print("Admin account already exists.")

        for item in DEFAULT_TEMPLATES:
            exists = NotificationTemplate.query.filter_by(title=item["title"]).first()
            if not exists:
                db.session.add(
                    NotificationTemplate(
                        title=item["title"],
                        category=item["category"],
                        content=item["content"],
                    )
                )
        db.session.commit()


if __name__ == "__main__":
    init_database()