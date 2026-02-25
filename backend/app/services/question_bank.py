from __future__ import annotations

from typing import Any

from app.models import DifficultyLevel, PreferredLanguage


def _pick(language: PreferredLanguage, *, ru: Any, kz: Any) -> Any:
    return ru if language == PreferredLanguage.ru else kz


QUESTION_BANK: dict[str, list[dict[str, Any]]] = {
    "математика": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Квадратные уравнения",
            "topic_kz": "Квадрат теңдеулер",
            "prompt_ru": "Какая формула дискриминанта квадратного уравнения ax^2 + bx + c = 0?",
            "prompt_kz": "ax^2 + bx + c = 0 квадрат теңдеуінің дискриминант формуласы қандай?",
            "options_ru": ["D = b^2 - 4ac", "D = b^2 + 4ac", "D = 2b - 4ac", "D = a^2 - 4bc"],
            "options_kz": ["D = b^2 - 4ac", "D = b^2 + 4ac", "D = 2b - 4ac", "D = a^2 - 4bc"],
            "correct_option_ids": [0],
            "explanation_ru": "Дискриминант квадратного уравнения вычисляется по формуле D = b^2 - 4ac.",
            "explanation_kz": "Квадрат теңдеудің дискриминанты D = b^2 - 4ac формуласы арқылы есептеледі.",
        },
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Квадратные уравнения",
            "topic_kz": "Квадрат теңдеулер",
            "prompt_ru": "Сколько действительных корней имеет квадратное уравнение при D < 0?",
            "prompt_kz": "D < 0 болғанда квадрат теңдеудің неше нақты түбірі болады?",
            "options_ru": ["Два", "Один", "Нет действительных корней", "Три"],
            "options_kz": ["Екі", "Бір", "Нақты түбір жоқ", "Үш"],
            "correct_option_ids": [2],
            "explanation_ru": "Если D < 0, квадратное уравнение не имеет действительных корней.",
            "explanation_kz": "Егер D < 0 болса, квадрат теңдеудің нақты түбірі болмайды.",
        },
        {
            "levels": ["easy", "medium"],
            "type": "single_choice",
            "topic_ru": "Линейные уравнения",
            "topic_kz": "Сызықтық теңдеулер",
            "prompt_ru": "Решите уравнение: 2x - 7 = 9",
            "prompt_kz": "Теңдеуді шешіңіз: 2x - 7 = 9",
            "options_ru": ["x = 6", "x = 7", "x = 8", "x = 9"],
            "options_kz": ["x = 6", "x = 7", "x = 8", "x = 9"],
            "correct_option_ids": [2],
            "explanation_ru": "2x = 16, поэтому x = 8.",
            "explanation_kz": "2x = 16, сондықтан x = 8.",
        },
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Геометрия",
            "topic_kz": "Геометрия",
            "prompt_ru": "Чему равна сумма внутренних углов треугольника?",
            "prompt_kz": "Үшбұрыштың ішкі бұрыштарының қосындысы неге тең?",
            "options_ru": ["90°", "120°", "180°", "360°"],
            "options_kz": ["90°", "120°", "180°", "360°"],
            "correct_option_ids": [2],
            "explanation_ru": "Сумма внутренних углов любого треугольника всегда равна 180°.",
            "explanation_kz": "Кез келген үшбұрыштың ішкі бұрыштарының қосындысы 180°.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Проценты",
            "topic_kz": "Пайыз",
            "prompt_ru": "Товар стоил 250 и подорожал на 20%. Какая новая цена?",
            "prompt_kz": "Тауар бағасы 250 болып, 20% өсті. Жаңа баға қанша?",
            "options_ru": ["270", "280", "295", "300"],
            "options_kz": ["270", "280", "295", "300"],
            "correct_option_ids": [3],
            "explanation_ru": "20% от 250 это 50. Новая цена: 250 + 50 = 300.",
            "explanation_kz": "250-дің 20%-ы 50. Жаңа баға: 250 + 50 = 300.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "multi_choice",
            "topic_ru": "Квадратные уравнения",
            "topic_kz": "Квадрат теңдеулер",
            "prompt_ru": "Выберите верные утверждения о дискриминанте D.",
            "prompt_kz": "D дискриминанты туралы дұрыс тұжырымдарды таңдаңыз.",
            "options_ru": [
                "Если D > 0, уравнение имеет два различных действительных корня",
                "Если D = 0, уравнение не имеет корней",
                "Если D < 0, действительных корней нет",
                "Если D = 0, уравнение имеет два различных корня",
            ],
            "options_kz": [
                "Егер D > 0 болса, теңдеудің екі әртүрлі нақты түбірі бар",
                "Егер D = 0 болса, теңдеудің түбірі жоқ",
                "Егер D < 0 болса, нақты түбір жоқ",
                "Егер D = 0 болса, теңдеудің екі әртүрлі түбірі бар",
            ],
            "correct_option_ids": [0, 2],
            "explanation_ru": "Для D > 0 два различных корня, для D = 0 один корень, для D < 0 нет действительных корней.",
            "explanation_kz": "D > 0 болса екі түрлі түбір, D = 0 болса бір түбір, D < 0 болса нақты түбір болмайды.",
        },
        {
            "levels": ["hard"],
            "type": "short_text",
            "topic_ru": "Квадратные уравнения",
            "topic_kz": "Квадрат теңдеулер",
            "prompt_ru": "Кратко объясните, как знак дискриминанта влияет на количество корней квадратного уравнения.",
            "prompt_kz": "Дискриминант таңбасы квадрат теңдеудің түбір санына қалай әсер ететінін қысқаша түсіндіріңіз.",
            "keywords_ru": ["дискриминант", "d>0", "d=0", "d<0"],
            "keywords_kz": ["дискриминант", "d>0", "d=0", "d<0"],
            "sample_answer_ru": "При D>0 уравнение имеет два корня, при D=0 один корень, при D<0 действительных корней нет.",
            "sample_answer_kz": "D>0 болса екі түбір, D=0 болса бір түбір, D<0 болса нақты түбір жоқ.",
            "explanation_ru": "Ключевой критерий числа корней квадратного уравнения это знак дискриминанта.",
            "explanation_kz": "Квадрат теңдеудің түбір саны дискриминант белгісіне тәуелді.",
        },
        {
            "levels": ["hard"],
            "type": "short_text",
            "topic_ru": "Квадратные уравнения",
            "topic_kz": "Квадрат теңдеулер",
            "prompt_ru": "Решите уравнение x^2 - 5x + 6 = 0 и укажите оба корня.",
            "prompt_kz": "x^2 - 5x + 6 = 0 теңдеуін шешіп, екі түбірін жазыңыз.",
            "keywords_ru": ["2", "3"],
            "keywords_kz": ["2", "3"],
            "sample_answer_ru": "Корни уравнения: x1 = 2 и x2 = 3.",
            "sample_answer_kz": "Түбірлері: x1 = 2 және x2 = 3.",
            "explanation_ru": "Произведение корней равно 6, а сумма равна 5, поэтому корни 2 и 3.",
            "explanation_kz": "Түбірлердің көбейтіндісі 6, қосындысы 5, сондықтан түбірлер 2 және 3.",
        },
    ],
    "алгебра": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Степени",
            "topic_kz": "Дәрежелер",
            "prompt_ru": "Чему равно выражение a^m * a^n?",
            "prompt_kz": "a^m * a^n өрнегі неге тең?",
            "options_ru": ["a^(m+n)", "a^(m-n)", "a^(mn)", "a^(m/n)"],
            "options_kz": ["a^(m+n)", "a^(m-n)", "a^(mn)", "a^(m/n)"],
            "correct_option_ids": [0],
            "explanation_ru": "При умножении степеней с одинаковым основанием показатели складываются.",
            "explanation_kz": "Бірдей негізді дәрежелер көбейтілсе, көрсеткіштер қосылады.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Неравенства",
            "topic_kz": "Теңсіздіктер",
            "prompt_ru": "Как изменится знак неравенства при умножении обеих частей на отрицательное число?",
            "prompt_kz": "Екі жағын теріс санға көбейткенде теңсіздік белгісі қалай өзгереді?",
            "options_ru": ["Не меняется", "Меняется на противоположный", "Исчезает", "Всегда становится >"],
            "options_kz": ["Өзгермейді", "Қарама-қарсыға өзгереді", "Жойылады", "Әрқашан > болады"],
            "correct_option_ids": [1],
            "explanation_ru": "При умножении/делении на отрицательное число знак неравенства меняется.",
            "explanation_kz": "Теріс санға көбейткенде/бөлгенде теңсіздік белгісі ауысады.",
        },
        {
            "levels": ["hard"],
            "type": "short_text",
            "topic_ru": "Квадратичная функция",
            "topic_kz": "Квадрат функция",
            "prompt_ru": "Кратко опишите, как коэффициент a в y = ax^2 + bx + c влияет на ветви параболы.",
            "prompt_kz": "y = ax^2 + bx + c формуласында a коэффициенті параболаның бағытына қалай әсер етеді?",
            "keywords_ru": ["a>0", "a<0", "вверх", "вниз"],
            "keywords_kz": ["a>0", "a<0", "жоғары", "төмен"],
            "sample_answer_ru": "Если a>0, ветви направлены вверх; если a<0, ветви направлены вниз.",
            "sample_answer_kz": "a>0 болса парабола жоғары, a<0 болса төмен ашылады.",
            "explanation_ru": "Знак коэффициента a определяет направление ветвей параболы.",
            "explanation_kz": "a коэффициентінің таңбасы параболаның бағытын анықтайды.",
        },
    ],
    "геометрия": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Теорема Пифагора",
            "topic_kz": "Пифагор теоремасы",
            "prompt_ru": "Какая формула верна для прямоугольного треугольника?",
            "prompt_kz": "Тікбұрышты үшбұрыш үшін қай формула дұрыс?",
            "options_ru": ["a^2 + b^2 = c^2", "a + b = c^2", "a^2 - b^2 = c^2", "2ab = c^2"],
            "options_kz": ["a^2 + b^2 = c^2", "a + b = c^2", "a^2 - b^2 = c^2", "2ab = c^2"],
            "correct_option_ids": [0],
            "explanation_ru": "В прямоугольном треугольнике сумма квадратов катетов равна квадрату гипотенузы.",
            "explanation_kz": "Тікбұрышты үшбұрышта катеттер квадраттарының қосындысы гипотенуза квадратына тең.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Площадь круга",
            "topic_kz": "Шеңбер ауданы",
            "prompt_ru": "Выберите формулу площади круга радиуса r.",
            "prompt_kz": "Радиусы r болатын шеңбер ауданының формуласын таңдаңыз.",
            "options_ru": ["S = 2πr", "S = πr^2", "S = πd", "S = r^2/π"],
            "options_kz": ["S = 2πr", "S = πr^2", "S = πd", "S = r^2/π"],
            "correct_option_ids": [1],
            "explanation_ru": "Площадь круга вычисляется по формуле S = πr^2.",
            "explanation_kz": "Шеңбер ауданы S = πr^2 формуласымен есептеледі.",
        },
    ],
    "физика": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Динамика",
            "topic_kz": "Динамика",
            "prompt_ru": "Как записывается второй закон Ньютона?",
            "prompt_kz": "Ньютонның екінші заңы қалай жазылады?",
            "options_ru": ["F = ma", "F = mv", "F = mg", "F = p/t"],
            "options_kz": ["F = ma", "F = mv", "F = mg", "F = p/t"],
            "correct_option_ids": [0],
            "explanation_ru": "Сила равна произведению массы на ускорение.",
            "explanation_kz": "Күш масса мен үдеудің көбейтіндісіне тең.",
        },
        {
            "levels": ["easy", "medium"],
            "type": "single_choice",
            "topic_ru": "Кинематика",
            "topic_kz": "Кинематика",
            "prompt_ru": "Какая формула скорости при равномерном движении?",
            "prompt_kz": "Бірқалыпты қозғалыста жылдамдық формуласы қандай?",
            "options_ru": ["v = s/t", "v = at", "v = s*t", "v = t/s"],
            "options_kz": ["v = s/t", "v = at", "v = s*t", "v = t/s"],
            "correct_option_ids": [0],
            "explanation_ru": "Скорость равна пройденному пути, деленному на время.",
            "explanation_kz": "Жылдамдық жүрілген жолдың уақытқа қатынасына тең.",
        },
    ],
    "русский язык": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Орфография",
            "topic_kz": "Орфография",
            "prompt_ru": "В каком слове пишется буква И?",
            "prompt_kz": "Қай сөзде И әрпі жазылады?",
            "options_ru": ["ц..тата", "ц..фра", "ц..плёнок", "ц..рк"],
            "options_kz": ["ц..тата", "ц..фра", "ц..плёнок", "ц..рк"],
            "correct_option_ids": [1],
            "explanation_ru": "В слове «цифра» после Ц пишется И.",
            "explanation_kz": "«цифра» сөзінде Ц әрпінен кейін И жазылады.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Пунктуация",
            "topic_kz": "Пунктуация",
            "prompt_ru": "Перед каким союзом обычно ставится запятая в сложносочиненном предложении?",
            "prompt_kz": "Салалас құрмаласта қай жалғаулық алдында әдетте үтір қойылады?",
            "options_ru": ["и", "а", "ли", "либо"],
            "options_kz": ["и", "а", "ли", "либо"],
            "correct_option_ids": [1],
            "explanation_ru": "Союз «а» часто соединяет части сложносочиненного предложения через запятую.",
            "explanation_kz": "«а» жалғаулығы бар бөліктер әдетте үтірмен бөлінеді.",
        },
    ],
    "английский язык": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Grammar",
            "topic_kz": "Грамматика",
            "prompt_ru": "Выберите правильную форму: She ___ to school every day.",
            "prompt_kz": "Дұрыс нұсқаны таңдаңыз: She ___ to school every day.",
            "options_ru": ["go", "goes", "is go", "going"],
            "options_kz": ["go", "goes", "is go", "going"],
            "correct_option_ids": [1],
            "explanation_ru": "В Present Simple с he/she/it используется форма с окончанием -s: goes.",
            "explanation_kz": "Present Simple-де he/she/it үшін -s жалғауы бар форма қолданылады: goes.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Tenses",
            "topic_kz": "Шақтар",
            "prompt_ru": "Выберите форму Past Simple для глагола go.",
            "prompt_kz": "go етістігінің Past Simple формасын таңдаңыз.",
            "options_ru": ["goed", "went", "gone", "goes"],
            "options_kz": ["goed", "went", "gone", "goes"],
            "correct_option_ids": [1],
            "explanation_ru": "Неправильный глагол go в Past Simple имеет форму went.",
            "explanation_kz": "go бұрыс етістігінің Past Simple формасы went болады.",
        },
    ],
    "биология": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Клетка",
            "topic_kz": "Жасуша",
            "prompt_ru": "Какая органелла отвечает за синтез АТФ в клетке?",
            "prompt_kz": "Жасушада АТФ синтезіне қай органелла жауап береді?",
            "options_ru": ["Ядро", "Митохондрия", "Рибосома", "Комплекс Гольджи"],
            "options_kz": ["Ядро", "Митохондрия", "Рибосома", "Гольджи кешені"],
            "correct_option_ids": [1],
            "explanation_ru": "Основной синтез АТФ в эукариотической клетке происходит в митохондриях.",
            "explanation_kz": "Эукариот жасушасында АТФ негізінен митохондрияда түзіледі.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Генетика",
            "topic_kz": "Генетика",
            "prompt_ru": "Как называется совокупность всех генов организма?",
            "prompt_kz": "Ағзаның барлық гендерінің жиынтығы қалай аталады?",
            "options_ru": ["Генотип", "Фенотип", "Кариотип", "Протеом"],
            "options_kz": ["Генотип", "Фенотип", "Кариотип", "Протеом"],
            "correct_option_ids": [0],
            "explanation_ru": "Генотип это совокупность генетической информации организма.",
            "explanation_kz": "Генотип ағзаның барлық генетикалық ақпаратын білдіреді.",
        },
    ],
    "информатика": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Системы счисления",
            "topic_kz": "Санау жүйелері",
            "prompt_ru": "Чему равно двоичное число 1010 в десятичной системе?",
            "prompt_kz": "1010 екілік саны ондық жүйеде неге тең?",
            "options_ru": ["8", "10", "12", "14"],
            "options_kz": ["8", "10", "12", "14"],
            "correct_option_ids": [1],
            "explanation_ru": "1010₂ = 8 + 2 = 10.",
            "explanation_kz": "1010₂ = 8 + 2 = 10.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Алгоритмы",
            "topic_kz": "Алгоритмдер",
            "prompt_ru": "Как называется алгоритм поиска по отсортированному массиву, делящий диапазон пополам?",
            "prompt_kz": "Сұрыпталған массивте аралықты екіге бөліп іздейтін алгоритм қалай аталады?",
            "options_ru": ["Линейный поиск", "Бинарный поиск", "Поиск в глубину", "Хеш-поиск"],
            "options_kz": ["Сызықтық іздеу", "Екілік іздеу", "Тереңдік бойынша іздеу", "Хэш іздеу"],
            "correct_option_ids": [1],
            "explanation_ru": "Бинарный поиск работает на отсортированном массиве, каждый шаг делит диапазон пополам.",
            "explanation_kz": "Екілік іздеу тек сұрыпталған массивте жұмыс істейді және аралықты екіге бөледі.",
        },
    ],
    "химия": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Неорганическая химия",
            "topic_kz": "Бейорганикалық химия",
            "prompt_ru": "Какая химическая формула воды?",
            "prompt_kz": "Судың химиялық формуласы қандай?",
            "options_ru": ["H2O", "CO2", "O2", "H2SO4"],
            "options_kz": ["H2O", "CO2", "O2", "H2SO4"],
            "correct_option_ids": [0],
            "explanation_ru": "Молекула воды состоит из двух атомов водорода и одного атома кислорода.",
            "explanation_kz": "Су молекуласы екі сутек және бір оттек атомынан тұрады.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Периодическая система",
            "topic_kz": "Периодтық жүйе",
            "prompt_ru": "Какой заряд имеет ядро атома натрия (Na)?",
            "prompt_kz": "Натрий (Na) атомы ядросының заряды қандай?",
            "options_ru": ["+11", "+23", "-11", "0"],
            "options_kz": ["+11", "+23", "-11", "0"],
            "correct_option_ids": [0],
            "explanation_ru": "Заряд ядра равен числу протонов, у Na это 11.",
            "explanation_kz": "Ядро заряды протон санына тең, Na үшін ол 11.",
        },
    ],
    "история": [
        {
            "levels": ["easy", "medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Вторая мировая война",
            "topic_kz": "Екінші дүниежүзілік соғыс",
            "prompt_ru": "В каком году началась Вторая мировая война?",
            "prompt_kz": "Екінші дүниежүзілік соғыс қай жылы басталды?",
            "options_ru": ["1914", "1939", "1941", "1945"],
            "options_kz": ["1914", "1939", "1941", "1945"],
            "correct_option_ids": [1],
            "explanation_ru": "Вторая мировая война началась 1 сентября 1939 года.",
            "explanation_kz": "Екінші дүниежүзілік соғыс 1939 жылғы 1 қыркүйекте басталды.",
        },
        {
            "levels": ["medium", "hard"],
            "type": "single_choice",
            "topic_ru": "Вторая мировая война",
            "topic_kz": "Екінші дүниежүзілік соғыс",
            "prompt_ru": "Какое событие принято считать непосредственным началом Второй мировой войны?",
            "prompt_kz": "Екінші дүниежүзілік соғыстың тікелей басталуы ретінде қай оқиға саналады?",
            "options_ru": [
                "Нападение Германии на Польшу",
                "Нападение Японии на Перл-Харбор",
                "Подписание Версальского договора",
                "Высадка союзников в Нормандии",
            ],
            "options_kz": [
                "Германияның Польшаға шабуылы",
                "Жапонияның Перл-Харборға шабуылы",
                "Версаль келісіміне қол қою",
                "Одақтастардың Нормандияға түсуі",
            ],
            "correct_option_ids": [0],
            "explanation_ru": "Именно нападение Германии на Польшу в сентябре 1939 стало триггером войны в Европе.",
            "explanation_kz": "1939 жылы Германияның Польшаға шабуылы Еуропадағы соғыстың басталуына түрткі болды.",
        },
        {
            "levels": ["hard"],
            "type": "short_text",
            "topic_ru": "Вторая мировая война",
            "topic_kz": "Екінші дүниежүзілік соғыс",
            "prompt_ru": "Охарактеризуйте главные причины начала Второй мировой войны.",
            "prompt_kz": "Екінші дүниежүзілік соғыстың басталуының негізгі себептерін сипаттаңыз.",
            "keywords_ru": ["версаль", "кризис", "агрессия", "германия"],
            "keywords_kz": ["версаль", "дағдарыс", "агрессия", "германия"],
            "sample_answer_ru": "Ключевые причины: последствия Версальского договора, мировой экономический кризис, рост реваншизма и агрессивная политика нацистской Германии.",
            "sample_answer_kz": "Негізгі себептер: Версаль келісімінің салдары, әлемдік экономикалық дағдарыс, реваншизмнің күшеюі және фашистік Германияның агрессивті саясаты.",
            "explanation_ru": "Причины войны носят комплексный характер: политический, экономический и идеологический.",
            "explanation_kz": "Соғыс себептері кешенді: саяси, экономикалық және идеологиялық факторлар.",
        },
    ],
}


DISTRACTOR_BANK: dict[str, dict[str, list[str]]] = {
    "математика": {
        "ru": [
            "Подстановка значений без учета знаков",
            "Перепутаны коэффициенты при вычислении",
            "Неверно применено правило сложения",
            "Игнорирован знак минус перед скобкой",
            "Сделан неверный переход в формуле",
        ],
        "kz": [
            "Белгілерді ескермей мәндерді қою",
            "Коэффициенттер шатастырылған",
            "Қосу ережесі қате қолданылған",
            "Жақша алдындағы минус ескерілмеген",
            "Формулада қате түрлендіру жасалған",
        ],
    },
    "история": {
        "ru": [
            "Смешаны причины и последствия события",
            "Перепутаны даты ключевых событий",
            "Неверно указан исторический контекст",
            "Подмена факта оценочным суждением",
            "Игнорирование международных факторов",
        ],
        "kz": [
            "Оқиғаның себебі мен салдары араластырылған",
            "Негізгі даталар шатастырылған",
            "Тарихи контекст қате көрсетілген",
            "Фактінің орнына бағалау пікірі берілген",
            "Халықаралық факторлар ескерілмеген",
        ],
    },
    "_default": {
        "ru": [
            "Неполное объяснение ключевого термина",
            "Смешение понятий из соседних тем",
            "Неверное применение основного правила",
            "Логический вывод не подтвержден фактом",
            "Пропущено важное условие задачи",
        ],
        "kz": [
            "Негізгі термин толық түсіндірілмеген",
            "Көршілес тақырып ұғымдары араласқан",
            "Негізгі ереже қате қолданылған",
            "Логикалық қорытынды фактпен расталмаған",
            "Есептің маңызды шарты ескерілмеген",
        ],
    },
}


SUBJECT_ALIASES: dict[str, str] = {
    "всемирная история": "история",
    "всемирнаяистория": "история",
    "тарих": "история",
    "дүниежүзі тарихы": "история",
    "дүниежүзітарихы": "история",
    "орыс тілі": "русский язык",
    "орыстили": "русский язык",
    "ағылшын тілі": "английский язык",
    "агылшын тілі": "английский язык",
    "агылшынтили": "английский язык",
}


def _normalize_subject_key(value: str) -> str:
    return " ".join(value.strip().lower().replace("ё", "е").split())


def _resolve_subject_key(subject_name_ru: str) -> str:
    normalized = _normalize_subject_key(subject_name_ru)
    if normalized in QUESTION_BANK:
        return normalized

    compact = normalized.replace(" ", "")
    if compact in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[compact]
    if normalized in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[normalized]
    return normalized


def get_text_question_templates(
    *,
    subject_name_ru: str,
    language: PreferredLanguage,
    difficulty: DifficultyLevel,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    key = _resolve_subject_key(subject_name_ru)
    templates = QUESTION_BANK.get(key, [])
    level = difficulty.value

    selected = []
    for item in templates:
        levels = [str(value) for value in item.get("levels", [])]
        if level not in levels and "all" not in levels:
            continue
        selected.append(
            {
                "type": item["type"],
                "topic": _pick(language, ru=item["topic_ru"], kz=item["topic_kz"]),
                "prompt": _pick(language, ru=item["prompt_ru"], kz=item["prompt_kz"]),
                "options": _pick(language, ru=item.get("options_ru"), kz=item.get("options_kz")),
                "correct_option_ids": list(item.get("correct_option_ids", [])),
                "keywords": _pick(language, ru=item.get("keywords_ru", []), kz=item.get("keywords_kz", [])),
                "sample_answer": _pick(language, ru=item.get("sample_answer_ru", ""), kz=item.get("sample_answer_kz", "")),
                "explanation": _pick(language, ru=item["explanation_ru"], kz=item["explanation_kz"]),
            }
        )

    if limit is not None:
        return selected[:limit]
    return selected


def get_distractors(*, subject_name_ru: str, language: PreferredLanguage) -> list[str]:
    key = _resolve_subject_key(subject_name_ru)
    lang_key = "ru" if language == PreferredLanguage.ru else "kz"
    subject_pool = DISTRACTOR_BANK.get(key, DISTRACTOR_BANK["_default"])
    return list(subject_pool.get(lang_key, DISTRACTOR_BANK["_default"][lang_key]))
