bl_info = {
    "name": "Pain(t)killer",
    "blender": (2, 80, 0),
    "category": "3D View",
    "location": "3D View > Sidebar > Pain(t)killer",
    "description": "Includes tools for toggling occlude and backface culling, and toggling image texture nodes between original and Linear interpolation and show overlay button",
}

import bpy

class PaintAndPreviewPanel(bpy.types.Panel):
    bl_label = "Pain(t)killer"
    bl_idname = "PAINT_PT_paint_and_preview"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Pain(t)killer'

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "paint_both_sides")
        layout.prop(scene.clean_preview_props, "toggle_clean_preview")

def update_paint_both_sides(self, context):
    settings = context.tool_settings.image_paint
    settings.use_occlude = not self.paint_both_sides
    settings.use_backface_culling = not self.paint_both_sides

class CleanPreviewProperties(bpy.types.PropertyGroup):
    toggle_clean_preview: bpy.props.BoolProperty(
        name="Clean Preview",
        description="Toggle all image texture nodes between original and Linear interpolation and toggle the show overlay button",
        default=False,
        update=lambda self, context: self.update_clean_preview(context)
    )
    previous_interpolations: bpy.props.CollectionProperty(type=bpy.types.PropertyGroup)
    previous_overlay_state: bpy.props.BoolProperty(default=True)

    def update_clean_preview(self, context):
        if self.toggle_clean_preview:
            self.previous_interpolations.clear()
            for mat in bpy.data.materials:
                if mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            item = self.previous_interpolations.add()
                            item.name = node.name
                            item["interpolation"] = node.interpolation
                            node.interpolation = 'Linear'
            self.previous_overlay_state = context.space_data.overlay.show_overlays
            context.space_data.overlay.show_overlays = False
        else:
            for mat in bpy.data.materials:
                if mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            for item in self.previous_interpolations:
                                if item.name == node.name:
                                    node.interpolation = item["interpolation"]
                                    break
            context.space_data.overlay.show_overlays = self.previous_overlay_state

classes = (
    PaintAndPreviewPanel,
    CleanPreviewProperties,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.paint_both_sides = bpy.props.BoolProperty(
        name="Paint Both Sides",
        description="Toggle occlude and backface culling",
        default=False,
        update=update_paint_both_sides
    )
    bpy.types.Scene.clean_preview_props = bpy.props.PointerProperty(type=CleanPreviewProperties)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.paint_both_sides
    del bpy.types.Scene.clean_preview_props

if __name__ == "__main__":
    register()
