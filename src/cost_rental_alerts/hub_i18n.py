"""Client-side translations for the Ireland Cost Rental Hub."""

from __future__ import annotations

import json

LANGUAGE_STORAGE_KEY = "crh_hub_lang"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "hub.title": {
        "en": "Ireland Cost Rental Hub",
        "pt": "Ireland Cost Rental Hub",
    },
    "hero.tagline": {
        "en": (
            "Cost rental schemes in Ireland — apply now and opening soon. "
            "Updated daily from cost rental portals"
        ),
        "pt": (
            "Esquemas de cost rental na Irlanda — candidaturas abertas e em breve. "
            "Atualizado diariamente a partir dos portais de cost rental"
        ),
    },
    "tip.sources": {
        "en": (
            "Data comes from Affordable Homes Ireland, LDA and Tuath Housing. Other "
            "cost-rental providers, including Clúid, Respond, Circle VHA, Co-operative "
            "Housing Ireland, Oaklee, Ó Cualann and Fold Ireland, usually publish their "
            "schemes through Affordable Homes Ireland, so they are covered there rather "
            "than listed separately."
        ),
        "pt": (
            "Os dados vêm da Affordable Homes Ireland, LDA e Tuath Housing. Outros "
            "fornecedores de cost rental, incluindo Clúid, Respond, Circle VHA, "
            "Co-operative Housing Ireland, Oaklee, Ó Cualann e Fold Ireland, costumam "
            "publicar os esquemas pela Affordable Homes Ireland, por isso aparecem lá "
            "em vez de serem listados separadamente."
        ),
    },
    "hero.updated": {"en": "Updated", "pt": "Atualizado"},
    "summary.apply_now": {"en": "🟢 Apply now", "pt": "🟢 Candidatar agora"},
    "summary.opening_soon": {"en": "🔵 Opening soon", "pt": "🔵 Em breve"},
    "summary.label": {
        "en": "Scheme summary",
        "pt": "Resumo dos esquemas",
    },
    "action.hub_actions": {"en": "Hub actions", "pt": "Ações do hub"},
    "action.email": {"en": "Email", "pt": "Email"},
    "action.report": {"en": "Report", "pt": "Reportar"},
    "action.about": {"en": "About", "pt": "Sobre"},
    "action.cost_rental": {"en": "Cost rental", "pt": "Cost rental"},
    "view.layout": {"en": "Layout", "pt": "Layout"},
    "view.table": {"en": "Table", "pt": "Tabela"},
    "view.cards": {"en": "Cards", "pt": "Cards"},
    "section.apply_now.title": {"en": "🟢 Apply now", "pt": "🟢 Candidatar agora"},
    "section.apply_now.tip": {
        "en": (
            "Open application windows. Schemes with a close date are sorted first so the "
            "earliest deadlines are easiest to spot. This app is in test phase. If you "
            "find inconsistencies, please use the Report button and we will work on "
            "fixing the problem."
        ),
        "pt": (
            "Janelas de candidatura abertas. Esquemas com data de encerramento aparecem "
            "primeiro para facilitar ver os prazos mais urgentes. Esta app está em fase "
            "de testes. Se encontrar inconsistências, use o botão Reportar e vamos "
            "corrigir o problema."
        ),
    },
    "section.apply_now.empty": {
        "en": "No schemes are open for applications right now.",
        "pt": "Nenhum esquema está aberto para candidaturas neste momento.",
    },
    "section.opening_soon.title": {"en": "🔵 Opening soon", "pt": "🔵 Em breve"},
    "section.opening_soon.tip": {
        "en": (
            "Not yet open for applications. Sorted by opening date, soonest first. "
            "This app is in test phase. If you find inconsistencies, please use the "
            "Report button and we will work on fixing the problem."
        ),
        "pt": (
            "Ainda não abertos para candidaturas. Ordenados por data de abertura, "
            "mais próximos primeiro. Esta app está em fase de testes. Se encontrar "
            "inconsistências, use o botão Reportar e vamos corrigir o problema."
        ),
    },
    "section.opening_soon.empty": {
        "en": "No schemes are opening soon right now.",
        "pt": "Nenhum esquema abre em breve neste momento.",
    },
    "count.scheme": {"en": "scheme", "pt": "esquema"},
    "count.schemes": {"en": "schemes", "pt": "esquemas"},
    "table.scheme": {"en": "Scheme", "pt": "Esquema"},
    "table.location": {"en": "📍 Location", "pt": "📍 Localização"},
    "table.price": {"en": "💰 Price", "pt": "💰 Preço"},
    "table.beds": {"en": "🛏️ Beds", "pt": "🛏️ Quartos"},
    "table.homes": {"en": "🏠 Homes", "pt": "🏠 Casas"},
    "table.income": {"en": "💶 Income", "pt": "💶 Rendimento"},
    "table.opens": {"en": "📅 Opens", "pt": "📅 Abre"},
    "table.closes": {"en": "⏰ Closes", "pt": "⏰ Fecha"},
    "table.apply_now": {"en": "Apply now", "pt": "Candidatar"},
    "detail.location": {"en": "📍 Location", "pt": "📍 Localização"},
    "detail.price": {"en": "💰 Price from", "pt": "💰 Preço desde"},
    "detail.homes": {"en": "🏠 Homes", "pt": "🏠 Casas"},
    "detail.beds": {"en": "🛏️ Bedrooms", "pt": "🛏️ Quartos"},
    "detail.income": {"en": "💶 Income", "pt": "💶 Rendimento"},
    "detail.opens": {"en": "📅 Opens", "pt": "📅 Abre"},
    "detail.closes": {"en": "⏰ Closes", "pt": "⏰ Fecha"},
    "value.not_listed": {"en": "Not listed", "pt": "Não indicado"},
    "value.tbc": {"en": "TBC", "pt": "A confirmar"},
    "value.unnamed": {"en": "Unnamed scheme", "pt": "Esquema sem nome"},
    "value.income_from": {"en": "From EUR", "pt": "Desde EUR"},
    "value.income_up_to": {"en": "Up to EUR", "pt": "Até EUR"},
    "status.open": {"en": "Open", "pt": "Aberto"},
    "status.opening_soon": {"en": "Opening Soon", "pt": "Em breve"},
    "report": {"en": "Report", "pt": "Reportar"},
    "tip.section_info": {"en": "Section information", "pt": "Informação da secção"},
    "lang.label": {"en": "Language", "pt": "Idioma"},
    "lang.en": {"en": "English", "pt": "Inglês"},
    "lang.pt": {"en": "Portuguese", "pt": "Português"},
    "modal.close": {"en": "Close", "pt": "Fechar"},
    "subscribe.title": {"en": "Get cost rental alerts", "pt": "Receber alertas de cost rental"},
    "subscribe.lede_line1": {
        "en": "Get free daily alerts for schemes you can apply for now, plus those opening soon.",
        "pt": "Alertas diários gratuitos com esquemas para candidatar agora e os que abrem em breve.",
    },
    "subscribe.lede_line2": {
        "en": "We check affordablehomes.ie, LDA, and Tuath Housing for you.",
        "pt": "Verificamos affordablehomes.ie, LDA e Tuath Housing por si.",
    },
    "subscribe.email": {"en": "Email", "pt": "Email"},
    "subscribe.consent": {
        "en": (
            "I agree to receive daily Ireland Cost Rental Alerts emails. "
            "You can unsubscribe at any time."
        ),
        "pt": (
            "Aceito receber emails diários do Ireland Cost Rental Alerts. "
            "Pode cancelar a subscrição a qualquer momento."
        ),
    },
    "subscribe.note": {
        "en": (
            "Double opt-in: we will send a confirmation email — click the link to "
            "finish subscribing."
        ),
        "pt": (
            "Confirmação dupla: enviaremos um email de confirmação — clique no link "
            "para concluir a subscrição."
        ),
    },
    "subscribe.submit": {"en": "Subscribe", "pt": "Subscrever"},
    "subscribe.not_now": {"en": "Not now", "pt": "Agora não"},
    "subscribe.success": {
        "en": "Almost there. Check your inbox and confirm your subscription.",
        "pt": "Quase lá. Verifique a caixa de entrada e confirme a subscrição.",
    },
    "subscribe.error": {
        "en": "Could not subscribe right now. Please try again.",
        "pt": "Não foi possível subscrever agora. Tente novamente.",
    },
    "about.title": {
        "en": "About Ireland Cost Rental Hub",
        "pt": "Sobre o Ireland Cost Rental Hub",
    },
    "about.lede": {
        "en": (
            "A daily dashboard for cost rental housing in Ireland. See what you can "
            "apply for today and what is opening soon, without checking each portal "
            "separately."
        ),
        "pt": (
            "Um painel diário de habitação cost rental na Irlanda. Veja o que pode "
            "candidatar-se hoje e o que abre em breve, sem consultar cada portal "
            "separadamente."
        ),
    },
    "about.how.title": {"en": "How it works", "pt": "Como funciona"},
    "about.how.body": {
        "en": (
            "We check affordablehomes.ie, LDA and Tuath Housing every morning, merge "
            "the results, and publish updates here and by email."
        ),
        "pt": (
            "Verificamos affordablehomes.ie, LDA e Tuath Housing todas as manhãs, "
            "unimos os resultados e publicamos atualizações aqui e por email."
        ),
    },
    "about.sources.title": {"en": "Data sources", "pt": "Fontes de dados"},
    "about.email.title": {"en": "Email alerts", "pt": "Alertas por email"},
    "about.email.body": {
        "en": "Get one morning email with apply-now and opening-soon schemes.",
        "pt": "Receba um email de manhã com esquemas abertos e em breve.",
    },
    "about.email.link": {"en": "Open email signup", "pt": "Abrir subscrição por email"},
    "about.test.title": {"en": "Test phase", "pt": "Fase de testes"},
    "about.test.body": {
        "en": (
            "This app is in test phase. If you find inconsistencies, please use the "
            "Report button and we will work on fixing the problem."
        ),
        "pt": (
            "Esta app está em fase de testes. Se encontrar inconsistências, use o "
            "botão Reportar e vamos corrigir o problema."
        ),
    },
    "about.limits.title": {
        "en": "Free service — some gaps",
        "pt": "Serviço gratuito — lacunas possíveis",
    },
    "about.limits.body": {
        "en": (
            "This hub is free to use. We read public portals automatically each morning, "
            "not by hand. Some details — like exact rent, income limits, or dates — may "
            "be missing when a portal does not show them clearly or changes layout. "
            "Always confirm on the official scheme page before you apply. Use Report if "
            "you spot a gap."
        ),
        "pt": (
            "Este hub é gratuito. Lemos os portais públicos automaticamente todas as "
            "manhãs, não manualmente. Alguns detalhes — como renda exata, limites de "
            "rendimento ou datas — podem faltar quando o portal não os mostra bem ou "
            "muda o layout. Confirme sempre na página oficial do esquema antes de "
            "candidatar-se. Use Reportar se encontrar uma lacuna."
        ),
    },
    "about.help.title": {"en": "Help improve this", "pt": "Ajude a melhorar"},
    "about.help.scheme": {
        "en": "Wrong details on a scheme? Use Report on that scheme's card.",
        "pt": "Detalhes errados num esquema? Use Reportar no card desse esquema.",
    },
    "about.help.report": {"en": "Send a report", "pt": "Enviar reporte"},
    "about.help.other": {"en": "Another problem?", "pt": "Outro problema?"},
    "about.help.contribute": {"en": "Want to contribute?", "pt": "Quer contribuir?"},
    "cost_rental.title": {"en": "What is cost rental?", "pt": "O que é cost rental?"},
    "cost_rental.lede": {
        "en": (
            "Cost rental is a form of affordable housing in Ireland where rent is set "
            "below market rates and linked to your household income."
        ),
        "pt": (
            "Cost rental é uma forma de habitação acessível na Irlanda em que a renda "
            "fica abaixo do mercado e ligada ao rendimento do agregado familiar."
        ),
    },
    "cost_rental.who.title": {"en": "Who provides it", "pt": "Quem fornece"},
    "cost_rental.who.body": {
        "en": (
            "Schemes are run by approved Irish housing bodies and public agencies, "
            "including Clúid, LDA and Tuath Housing. Many others publish through "
            "Affordable Homes Ireland."
        ),
        "pt": (
            "Os esquemas são geridos por entidades de habitação irlandesas aprovadas e "
            "agências públicas, incluindo Clúid, LDA e Tuath Housing. Muitos outros "
            "publicam pela Affordable Homes Ireland."
        ),
    },
    "cost_rental.diff.title": {"en": "How it differs", "pt": "Em que difere"},
    "cost_rental.diff.body": {
        "en": (
            "Unlike HAP or the Rental Accommodation Scheme, cost rental is a tenancy in "
            "a new affordable home — not a subsidy for a home you find yourself. It is "
            "also different from traditional social housing queues, though eligibility "
            "can overlap."
        ),
        "pt": (
            "Ao contrário do HAP ou do Rental Accommodation Scheme, cost rental é um "
            "arrendamento numa casa nova acessível — não um subsídio para uma casa que "
            "encontra por conta própria. Também difere das filas tradicionais de "
            "habitação social, embora a elegibilidade possa sobrepor-se."
        ),
    },
    "cost_rental.apply.title": {"en": "How to apply", "pt": "Como candidatar-se"},
    "cost_rental.apply.body": {
        "en": (
            "When a scheme is open, apply through the provider's portal — "
            "affordablehomes.ie, LDA or Tuath Housing. This hub shows what is open now "
            "and opening soon so you do not miss a window."
        ),
        "pt": (
            "Quando um esquema está aberto, candidate-se no portal do fornecedor — "
            "affordablehomes.ie, LDA ou Tuath Housing. Este hub mostra o que está "
            "aberto agora e em breve para não perder o prazo."
        ),
    },
}


def translations_json() -> str:
    return json.dumps(TRANSLATIONS, ensure_ascii=False)
