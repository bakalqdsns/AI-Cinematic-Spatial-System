"""
Automatic prompt vocabulary for Grounding DINO.

Instead of requiring a VLM (DashScope) to generate object class lists,
we use rich, pre-defined scene-specific word tables that are comprehensive
enough to cover the vast majority of common objects in each scene type.

The "universal" fallback is a superset of all categories, safe for any image.
"""

# ─── Scene-specific word tables ────────────────────────────────────────────────
# Each value is a dot-separated list of class names, matching the format
# Grounding DINO expects (either dot-separated or comma-separated).

SCENE_PROMPTS: dict[str, str] = {
    "universal": (
        "person.people.man.woman.child.building.house.skyscraper.tower.window.door."
        "tree.trees.plant.bush.shrub.grass.ground.floor.road.street.sidewalk.path."
        "car.suv.truck.van.bus.vehicle.bicycle.motorcycle.wheel.tire."
        "sky.cloud.clouds.mountain.hill.rock.stone.water.river.lake.sea.ocean.pond."
        "bridge.fence.railing.pillar.post.lamp.streetlamp.light.traffic.light.sign."
        "bench.table.chair.sofa.cabinet.shelf.bed.curtain.blind."
        "animal.dog.cat.bird.horses.cow.sheep.goat.fish."
        "flower.leaf.vegetation.branch.trunk.wood.bark."
        "sand.dirt.mud.snow.ice.rain.fog.smoke.steam."
        "boat.ship.airplane.plane.train.railway.tunnel."
        "wall.ceiling.roof.chimney.balcony.tower.antenna."
        "food.dish.bowl.plate.cup.bottle.glass.basket.bag.package.box.crate."
        "screen.monitor.keyboard.mouse.telephone.book.painting.photo.frame."
        "ball.bottle.umbrella.bag.backpack.handbag.suitcase."
        "helmet.hat.glasses.jewelry.watch.shirt.pants.shoes.sneakers."
        "coworker.student.teacher.driver.passenger.pedestrian.cyclist."
        "shadow.reflection.puddle.ripple.wave.splash."
        "traffic.cone.barrier.gate.wall.brick.concrete.metal.glass.wood.plastic."
        "helmet.hat.glasses.jewelry.watch.shirt.pants.shoes.sneakers"
    ),
    "outdoor": (
        "person.people.man.woman.child.pedestrian.driver.passenger.cyclist."
        "car.suv.truck.van.bus.vehicle.bicycle.motorcycle.taxi.ambulance.police car."
        "building.house.skyscraper.tower.factory.warehouse.shop.stall."
        "tree.trees.plant.bush.shrub.grass.ground.vegetation.park.garden."
        "sky.cloud.clouds.mountain.hill.rock.stone.boulder.cliff."
        "road.street.sidewalk.path.lane.crosswalk.parking.lot.railway.track."
        "bridge.fence.railing.pillar.post.lamp.streetlamp.traffic light.sign.signal."
        "bench.table.waste bin.recycling bin.mailbox.fire hydrant.bollard."
        "animal.dog.cat.bird.horses.squirrel.pigeon.seagull.crow."
        "water.river.stream.lake.pond.fountain.pool.puddle.rain.wet ground."
        "shadow.reflection.ripple.wave.splash.fog.smoke.steam."
        "traffic cone.barrier.concrete barrier.gate.barricade.tape."
        "boat.ship.airplane.plane.train.railway.tunnel.platform.station."
        "construction.scaffold.crane.excavator.bulldozer.dump truck.cement mixer."
        "sign.billboard.advertisement.notice.warning.information.speed limit."
        "food stall.market.stand.umbrella.awning.canopy.tent"
    ),
    "indoor": (
        "person.people.man.woman.child.worker.guest.customer.patient.student."
        "chair.sofa.couch.stool.office chair.gaming chair.rocking chair."
        "table.desk.dining table.coffee table.nightstand.drawer cabinet."
        "bed.bunk bed.couch.bench.ottoman.pouf.beanbag."
        "wall.ceiling.floor.door.window.curtain.blind.shade.shelf.cabinet."
        "bookshelf.wardrobe.cupboard.cabinet.closet.drawer.case."
        "lamp.floor lamp.desk lamp.ceiling light.chandelier.sconce.neon.light."
        "screen.monitor.tv.television.laptop.tablet.phone.telephone.keyboard.mouse."
        "book.magazine.newspaper.paper.document.notebook.photo.frame.painting."
        "plant.potted plant.flower.vase.bouquet.leaf.tree.bonsai.terrarium."
        "food.dish.plate.bowl.cup.mug.glass.bottle.jar.container.pot.pan."
        "kitchen appliance.refrigerator.microwave.oven.stove.hood.toaster.blender."
        "sink.faucet.shower.bathtub.toilet.bidet.towel.rack.bathroom mirror."
        "stairs.staircase.railing.handrail.elevator.lift.escalator."
        "floor.rug.carpet.tile.wood floor.laminate.vinyl.marble.granite."
        "shadow.reflection.window.light fixture.candle.fireplace.heater.ac.unit."
        "toy.game.puzzle.figurine.doll.action figure.board game.card game."
        "luggage.backpack.handbag.briefcase.suitcase.bag.case.purse."
        "coat.hat.scarf.gloves.boots.shoes.sneakers.slipper.umbrella"
    ),
    "night": (
        "person.people.man.woman.child.pedestrian.driver.passenger.nightclubber."
        "car.suv.truck.van.bus.taxi.ambulance.police car.vehicle.light."
        "building.house.skyscraper.tower.sign.billboard.neon sign.LED sign."
        "streetlamp.lamp.post.light fixture.traffic light.signal.flasher."
        "headlight.taillight.brake light.turn signal.fog light.interior light."
        "window.lit window.glowing window.dark window.reflection.glass."
        "sky.night sky.stars.moon.cloud.fog.smoke.steam.haze."
        "tree.trees.plant.shadow.sign.post.pillar.railing.fence.wall."
        "neon.neon light.neon sign.LED screen.display.billboard.lightbox."
        "fire.fireplace.campfire.candle.torch.flame.spark.lamp.lantern."
        "water.reflected light.ripple.wave.puddle.wet road.shimmer.glitter."
        "animal.dog.cat.bird.bat.owl.insect.firefly.moth."
        "person silhouette.shadow figure.backlit figure.outline.presence."
        "vehicle light trail.light trail.star trail.motion blur.long exposure."
        "barrier.cone.gate.wall.railing.bollard.post.concrete barrier."
        "sign.signal.warning.notice.advertisement.flashing light.blinking light"
    ),
    "nature": (
        "tree.trees.forest.woodland.grove.plantation.palm.tree.pine.oak.maple.birch."
        "plant.bush.shrub.grass.ground.vegetation.moss.fern.fern.liana.vine."
        "mountain.hill.rock.stone.boulder.cliff.ridge.canyon.valley.cave.grotto."
        "sky.cloud.clouds.mist.fog.haze.smoke.steam.rain.rainbow."
        "water.river.stream.creek.waterfall.spring.pond.lake.sea.ocean.wave.splash."
        "sand.beach.dune.desert.shore.shoreline.bank.grassland.meadow.field."
        "snow.ice.glacier.iceberg.snowflake.frost.hail.sleet.blizzard.avalanche."
        "animal.dog.cat.bird.horses.cow.sheep.goat.pig.elephant.lion.tiger.bear."
        "bird.eagle.hawk.owl.raven.crow.sparrow.pigeon.seagull.crane.heron.swan."
        "fish.shark.whale.dolphin.jellyfish.coral.seaweed.turtle.sea lion.seal."
        "insect.bee.wasp.butterfly.moth.dragonfly.grasshopper.beetle.ant.spider."
        "flower.petal.pollen.stamen.pistil.blossom.bloom.bud.leaf.needles."
        "dirt.mud.sand.gravel.pebble.rock.granite.limestone.sandstone.clay.soil."
        "shadow.reflection.ripple.splash.footprint.track.trail.paw.print.hoof.print."
        "path.trail.footpath.hiking trail.dirt road.wooden bridge.log bridge."
        "tent.cabin.hut.shelter.yurt.campsite.campfire.lantern.torch."
        "sun.sunrise.sunset.sunlight.moonlight.starlight.twilight.dawn.dusk"
    ),
}


# ─── Scene detection (simple heuristics, no model needed) ─────────────────────

# These are used when VLM is not available, to pick the most appropriate prompt.
# We infer the scene type from image statistics (brightness, color distribution).


def infer_scene_from_image(image: "Image.Image") -> str:  # noqa: F821
    """
    Heuristic scene type inference from image pixels — no model needed.

    Uses color channel statistics to guess the scene type:
    - nature: high green channel mean
    - night: low overall brightness
    - indoor: low blue (walls often warm), moderate brightness
    - outdoor: default fallback
    """
    import numpy as np

    img_np = np.array(image.convert("RGB"))
    mean_brightness = img_np.mean()
    mean_green = img_np[:, :, 1].mean()
    mean_blue = img_np[:, :, 2].mean()

    # Normalize green vs blue to detect nature vs indoor
    green_ratio = mean_green / (mean_brightness + 1e-6)

    if mean_brightness < 60:
        return "night"
    if green_ratio > 1.05:
        return "nature"
    if mean_blue < 80 and mean_brightness < 150:
        return "indoor"
    return "outdoor"


def get_auto_prompt(scene_type: str | None = None) -> str:
    """
    Return a dot-separated class name string for Grounding DINO.

    Args:
        scene_type: One of "universal", "outdoor", "indoor", "night", "nature".
                   If None, returns the universal prompt.

    Returns:
        Dot-separated lowercase class names, e.g.
        "person.car.building.tree.sky.road.grass.mountain.water"
    """
    return SCENE_PROMPTS.get(scene_type, SCENE_PROMPTS["universal"])
