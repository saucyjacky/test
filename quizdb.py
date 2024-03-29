from discord.ext import commands
from html import unescape

import question


class DB(commands.Cog):
    def __init__(self, bot):
        self.conn = bot.pool

    async def get_tossups(self, category=None, number=1):
        if not category:
            data = await self.conn.fetch("select tossups.text, tossups.formatted_answer, categories.name, tournaments.name from tossups "
                                         "join tournaments on tossups.tournament_id = tournaments.id and tournaments.difficulty in (2,3,4,5) "
                                         "join categories on tossups.category_id = categories.id "
                                         "WHERE tossups.formatted_answer like '%<strong>%' or position(' ' in formatted_answer) <= 0 "
                                         "or tossups.formatted_answer similar to '[a-zA-Z]+\s<[^strong^em^u>^b>]%'"
                                         "ORDER BY RANDOM() LIMIT {}".format(number))
        else:
            data = await self.conn.fetch("select tossups.text, tossups.formatted_answer, categories.name, tournaments.name from tossups "
                                         "join tournaments on tossups.tournament_id = tournaments.id and tournaments.difficulty in (2,3,4,5) "
                                         "join categories on tossups.category_id = categories.id "
                                         "WHERE (tossups.formatted_answer like '%<strong>%' or position(' ' in formatted_answer) <= 0 "
                                         "or tossups.formatted_answer similar to '[a-zA-Z]+\s<[^strong^em^u>^b>]%') "
                                         "and lower(categories.name) = lower('{0}')"
                                         "ORDER BY RANDOM() LIMIT {1}".format(category, number))
        data = data[0]

        return question.Tossup(unescape(data[0]), unescape(data[1]), data[2], data[3], "(*)" in unescape(data[0]))

    async def get_bonuses(self, number=1):
        data = await self.conn.fetch("with A2 as (select bonuses.id, tournaments.name, leadin, bonuses.category_id from bonuses "
                                     "join tournaments on bonuses.tournament_id=tournaments.id and tournaments.difficulty in (2,3,4,5)) "
                                     "select leadin, array_agg(bonus_parts.text order by bonus_parts.id), "
                                     "array_agg(bonus_parts.formatted_answer order by bonus_parts.id) as ans, "
                                     "categories.name, A2.name from bonus_parts join A2 on bonus_parts.bonus_id = A2.id "
                                     "join categories on A2.category_id = categories.id "
                                     "group by categories.name, A2.name, bonus_id, leadin "
                                     "having (array_agg(bonus_parts.formatted_answer))[1] like '%<strong>%' "
                                     "or (position(' ' in (array_agg(bonus_parts.formatted_answer))[1]) <= 0 "
                                     "and position(' ' in (array_agg(bonus_parts.formatted_answer))[2]) <= 0 "
                                     "and position(' ' in (array_agg(bonus_parts.formatted_answer))[3]) <= 0) "
                                     "order by random() limit {}".format(number))
        return question.Bonus(data[0], [unescape(x) for x in data[1]], [unescape(x) for x in data[2]], data[3], data[4])

    async def get_ms(self, number=1):
        data = await self.conn.fetch("select tossups.text, tossups.formatted_answer, categories.name, tournaments.name from tossups "
                                     "join tournaments on tossups.tournament_id = tournaments.id and tournaments.difficulty = 1 "
                                     "join categories on tossups.category_id = categories.id "
                                     "order by random() limit {}".format(number))
        data = data[0]
        return question.Tossup(unescape(data[0]), unescape(data[1]), data[2], data[3], "(*)" in unescape(data[0]))
