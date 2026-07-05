"""
Arbitration clause templates based on Portuguese law (Lei n.º 63/2011).

Three types:
- ad_hoc: UNCITRAL rules, custom arbiter/city
- institutional: CAC rules, Lisbon
- escalated: ad hoc first → CAC second (cláusula arbitral escalonada)

Portuguese templates are legally valid. Other languages are informational translations only.
"""

TEMPLATES = {
    'ad_hoc': {
        'pt': (
            'Cláusula Arbitral: Todos os litígios decorrentes ou relacionados com '
            'este contrato serão resolvidos por arbitragem ad hoc, conduzida por '
            '{arbiter_name} como árbitro, de acordo com as Regras de Arbitragem da '
            'UNCITRAL. A arbitragem terá lugar em {city}, Portugal, e a língua da '
            'arbitragem será o português. O número de árbitros será um (1). '
            'A decisão arbitral será final e vinculativa.'
        ),
        'en': (
            'Arbitration Clause: All disputes arising out of or in connection with '
            'this contract shall be resolved by ad hoc arbitration, conducted by '
            '{arbiter_name} as arbitrator, in accordance with the UNCITRAL '
            'Arbitration Rules. The seat of arbitration shall be {city}, Portugal, '
            'and the language of the arbitration shall be Portuguese. The number '
            'of arbitrators shall be one (1). The arbitral award shall be final '
            'and binding. [Informational translation — Portuguese version prevails]'
        ),
        'es': (
            'Cláusula Arbitral: Todas las disputas derivadas o relacionadas con '
            'este contrato serán resueltas por arbitraje ad hoc, conducido por '
            '{arbiter_name} como árbitro, de acuerdo con las Reglas de Arbitraje '
            'de la UNCITRAL. El arbitraje tendrá lugar en {city}, Portugal, y el '
            'idioma del arbitraje será el portugués. El número de árbitros será '
            'uno (1). La decisión arbitral será final y vinculante. '
            '[Traducción informativa — la versión portuguesa prevalece]'
        ),
        'fr': (
            'Clause Arbitrale: Tous les litiges découlant de ou en relation avec '
            'ce contrat seront résolus par arbitrage ad hoc, conduit par '
            '{arbiter_name} en tant qu\'arbitre, conformément au Règlement '
            'd\'Arbitrage de la CNUDCI. L\'arbitrage aura lieu à {city}, Portugal, '
            'et la langue de l\'arbitrage sera le portugais. Le nombre d\'arbitres '
            'sera un (1). La sentence arbitrale sera définitive et obligatoire. '
            '[Traduction informative — la version portugaise prévaut]'
        ),
        'de': (
            'Schiedsklausel: Alle Streitigkeiten aus oder im Zusammenhang mit '
            'diesem Vertrag werden durch Ad-hoc-Schiedsverfahren beigelegt, '
            'durchgeführt von {arbiter_name} als Schiedsrichter, gemäß den '
            'UNCITRAL-Schiedsregeln. Der Schiedsort ist {city}, Portugal, und '
            'die Sprache des Schiedsverfahrens ist Portugiesisch. Die Anzahl der '
            'Schiedsrichter beträgt eins (1). Der Schiedsspruch ist endgültig '
            'und bindend. [Informative Übersetzung — die portugiesische Fassung '
            'hat Vorrang]'
        ),
        'ru': (
            'Арбитражная оговорка: Все споры, возникающие из данного договора '
            'или в связи с ним, будут разрешены путём арбитража ad hoc под '
            'руководством {arbiter_name} в качестве арбитра, в соответствии с '
            'Арбитражным регламентом ЮНСИТРАЛ. Арбитраж будет проводиться в '
            '{city}, Португалия, на португальском языке. Количество арбитров — '
            'один (1). Арбитражное решение является окончательным и обязательным. '
            '[Информационный перевод — португальская версия имеет приоритет]'
        ),
    },

    'institutional': {
        'pt': (
            'Cláusula Arbitral: Todos os litígios decorrentes ou relacionados com '
            'este contrato, incluindo questões relativas à sua existência, validade '
            'ou resolução, serão submetidos e resolvidos definitivamente por '
            'arbitragem institucional sob as Regras de Arbitragem do Centro de '
            'Arbitragem Comercial da Câmara de Comércio e Indústria Portuguesa '
            '(CAC). A arbitragem terá lugar em Lisboa, Portugal, e a língua da '
            'arbitragem será o português. O número de árbitros será um (1), salvo '
            'acordo em contrário das partes. A decisão arbitral será final e '
            'vinculativa, equiparável a uma sentença de um tribunal de primeira '
            'instância, e as partes renunciam a qualquer recurso judicial, exceto '
            'nos casos previstos na lei.'
        ),
        'en': (
            'Arbitration Clause: All disputes arising out of or in connection with '
            'this contract, including any question regarding its existence, validity '
            'or termination, shall be submitted to and finally resolved by '
            'institutional arbitration under the Arbitration Rules of the Commercial '
            'Arbitration Centre of the Portuguese Chamber of Commerce and Industry '
            '(CAC). The seat of arbitration shall be Lisbon, Portugal, and the '
            'language of the arbitration shall be Portuguese. The number of '
            'arbitrators shall be one (1), unless otherwise agreed by the parties. '
            'The arbitral award shall be final and binding, equivalent to a '
            'first-instance court judgment. '
            '[Informational translation — Portuguese version prevails]'
        ),
        'es': (
            'Cláusula Arbitral: Todas las disputas derivadas o relacionadas con '
            'este contrato, incluyendo cualquier cuestión relativa a su existencia, '
            'validez o resolución, serán sometidas y resueltas definitivamente por '
            'arbitraje institucional bajo las Reglas de Arbitraje del Centro de '
            'Arbitraje Comercial de la Cámara de Comercio e Industria Portuguesa '
            '(CAC). El arbitraje tendrá lugar en Lisboa, Portugal. El laudo arbitral '
            'será final y vinculante. '
            '[Traducción informativa — la versión portuguesa prevalece]'
        ),
        'fr': (
            'Clause Arbitrale: Tous les litiges découlant de ou en relation avec '
            'ce contrat seront soumis et définitivement résolus par arbitrage '
            'institutionnel selon le Règlement d\'Arbitrage du Centre d\'Arbitrage '
            'Commercial de la Chambre de Commerce et d\'Industrie Portugaise (CAC). '
            'L\'arbitrage aura lieu à Lisbonne, Portugal. La sentence arbitrale sera '
            'définitive et obligatoire. '
            '[Traduction informative — la version portugaise prévaut]'
        ),
        'de': (
            'Schiedsklausel: Alle Streitigkeiten aus oder im Zusammenhang mit '
            'diesem Vertrag werden der institutionellen Schiedsgerichtsbarkeit '
            'nach den Schiedsregeln des Handelsschiedszentrums der Portugiesischen '
            'Industrie- und Handelskammer (CAC) unterworfen. Schiedsort ist '
            'Lissabon, Portugal. Der Schiedsspruch ist endgültig und bindend. '
            '[Informative Übersetzung — die portugiesische Fassung hat Vorrang]'
        ),
        'ru': (
            'Арбитражная оговорка: Все споры, возникающие из данного договора '
            'или в связи с ним, будут переданы и окончательно разрешены путём '
            'институционального арбитража в соответствии с Арбитражным регламентом '
            'Центра коммерческого арбитража Торгово-промышленной палаты Португалии '
            '(CAC). Арбитраж будет проводиться в Лиссабоне, Португалия. Арбитражное '
            'решение является окончательным и обязательным. '
            '[Информационный перевод — португальская версия имеет приоритет]'
        ),
    },

    'escalated': {
        'pt': (
            'Cláusula Arbitral: Todos os litígios decorrentes ou relacionados com '
            'este contrato, incluindo questões relativas à sua existência, validade '
            'ou resolução, serão resolvidos, em primeira instância, por arbitragem '
            'ad hoc, conduzida por {arbiter_name} como árbitro, na cidade de '
            '{city}, Portugal, na língua portuguesa, seguindo as Regras de '
            'Arbitragem da UNCITRAL, salvo acordo em contrário das partes. '
            'Caso qualquer das partes não aceite a decisão da arbitragem ad hoc, '
            'o litígio será submetido, em segunda instância, a arbitragem '
            'institucional sob as Regras de Arbitragem do Centro de Arbitragem '
            'Comercial da Câmara de Comércio e Indústria Portuguesa (CAC), com um '
            'árbitro, em Lisboa, Portugal, na língua portuguesa. A decisão do CAC '
            'será final e vinculativa, sem possibilidade de recurso, exceto nos '
            'casos previstos na Lei n.º 63/2011, de 14 de dezembro.'
        ),
        'en': (
            'Arbitration Clause: All disputes arising out of or in connection with '
            'this contract shall be resolved, in the first instance, by ad hoc '
            'arbitration conducted by {arbiter_name} as arbitrator in {city}, '
            'Portugal, in Portuguese, following the UNCITRAL Arbitration Rules. '
            'Should either party not accept the ad hoc arbitration decision, the '
            'dispute shall be submitted, in the second instance, to institutional '
            'arbitration under the Arbitration Rules of the Commercial Arbitration '
            'Centre of the Portuguese Chamber of Commerce and Industry (CAC), with '
            'one arbitrator, in Lisbon, Portugal, in Portuguese. The CAC decision '
            'shall be final and binding, without possibility of appeal, except as '
            'provided by Law No. 63/2011 of 14 December. '
            '[Informational translation — Portuguese version prevails]'
        ),
        'es': (
            'Cláusula Arbitral: Todas las disputas serán resueltas, en primera '
            'instancia, por arbitraje ad hoc conducido por {arbiter_name} en '
            '{city}, Portugal. Si alguna de las partes no acepta la decisión, el '
            'litigio será sometido al CAC en Lisboa. La decisión del CAC será final '
            'y vinculante. '
            '[Traducción informativa — la versión portuguesa prevalece]'
        ),
        'fr': (
            'Clause Arbitrale: Tous les litiges seront résolus, en première '
            'instance, par arbitrage ad hoc conduit par {arbiter_name} à {city}, '
            'Portugal. Si une partie n\'accepte pas la décision, le litige sera '
            'soumis au CAC à Lisbonne. La décision du CAC sera définitive et '
            'obligatoire. '
            '[Traduction informative — la version portugaise prévaut]'
        ),
        'de': (
            'Schiedsklausel: Alle Streitigkeiten werden zunächst durch Ad-hoc-'
            'Schiedsverfahren unter {arbiter_name} in {city}, Portugal, beigelegt. '
            'Akzeptiert eine Partei die Entscheidung nicht, wird der Streit dem '
            'CAC in Lissabon vorgelegt. Die Entscheidung des CAC ist endgültig und '
            'bindend. '
            '[Informative Übersetzung — die portugiesische Fassung hat Vorrang]'
        ),
        'ru': (
            'Арбитражная оговорка: Все споры будут разрешены в первой инстанции '
            'путём арбитража ad hoc под руководством {arbiter_name} в {city}, '
            'Португалия. Если одна из сторон не примет решение, спор будет передан '
            'в CAC в Лиссабоне. Решение CAC является окончательным и обязательным. '
            '[Информационный перевод — португальская версия имеет приоритет]'
        ),
    },
}


def generate_clause(clause_type: str, lang: str = 'pt',
                    arbiter_name: str = '', city: str = 'Lisboa') -> str:
    """Generate an arbitration clause text.

    Args:
        clause_type: 'ad_hoc', 'institutional', or 'escalated'
        lang: Language code (pt, en, es, fr, de, ru)
        arbiter_name: Arbiter name (required for ad_hoc and escalated)
        city: City for arbitration seat (default: Lisboa)

    Returns:
        Formatted clause text
    """
    template_group = TEMPLATES.get(clause_type)
    if not template_group:
        return ''

    template = template_group.get(lang) or template_group.get('pt', '')
    return template.format(arbiter_name=arbiter_name or '[nome do árbitro]',
                           city=city or 'Lisboa')
