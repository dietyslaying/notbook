from interfaces import UIComponent

class ComponentPolicy:
    @staticmethod
    def map_to_ui_components(ndm_data: dict) -> list[UIComponent]:
        if "error" in ndm_data:
            return [UIComponent(component_type="error", data=ndm_data["error"])]

        components = []
        
        # 1. Title Component
        components.append(UIComponent(
            component_type="title",
            data=ndm_data.get("title", "Unknown Topic")
        ))
        
        # 2. Summary Component
        components.append(UIComponent(
            component_type="summary",
            data=ndm_data.get("summary", "")
        ))
        
        # 3. Fact List Component
        components.append(UIComponent(
            component_type="fact_list",
            data=ndm_data.get("core_facts", [])
        ))
        
        # 4. Collapsible Details Component
        components.append(UIComponent(
            component_type="collapsible",
            data=ndm_data.get("expandable_details", "")
        ))
        
        # 5. Source Component
        components.append(UIComponent(
            component_type="source",
            data=ndm_data.get("source_citation", "Unknown Source")
        ))
        
        return components
