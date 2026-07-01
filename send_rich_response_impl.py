    import json
    from ndm_validator import NDMValidator
    from enrichment.decorators import EnrichmentPipeline
    from layout.presentation_engine import PresentationEngine
    from layout.template_registry import TemplateRegistry
    from layout.page_builder import PageBuilder
    from engine.interaction_engine import InteractionEngine
    from engine.render_planner import RenderPlanner
    from renderers.backends.telegram_rich_backend import TelegramRichBackend
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    try:
        final_ast = json.loads(full_answer)
    except Exception:
        from partial_json_parser import parse_partial_json
        final_ast = parse_partial_json(full_answer)

    validator = NDMValidator()
    enricher = EnrichmentPipeline()
    presentation_engine = PresentationEngine()
    template_registry = TemplateRegistry(presentation_engine)
    page_builder = PageBuilder(template_registry)
    interaction = InteractionEngine()
    render_planner = RenderPlanner(interaction)
    renderer = TelegramRichBackend()

    valid_tree = validator.validate(final_ast)
    enriched_tree = enricher.enrich(valid_tree)
    doc = page_builder.build_page(enriched_tree)

    streaming_plan, interaction_tree = render_planner.plan(doc)
    final_html = renderer.render_streaming_plan(streaming_plan)
    keyboard_markup = renderer.build_inline_keyboard(interaction_tree)

    markup = None
    if keyboard_markup:
        markup = InlineKeyboardMarkup(inline_keyboard=[])
        for row in keyboard_markup.get("inline_keyboard", []):
            markup.inline_keyboard.append([
                InlineKeyboardButton(text=btn["text"], callback_data=btn["callback_data"])
                for btn in row
            ])

    await message.answer(final_html[:4000], parse_mode="HTML", reply_markup=markup)
