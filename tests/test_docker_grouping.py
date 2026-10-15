"""Testy seskupovani Docker kontejneru podle Compose projektu.

`docker ps --format '{{json .}}'` vraci pole `Labels` jako jeden retezec
`klic=hodnota` spojeny carkami - a hodnota sama muze carku obsahovat:

    com.docker.compose.depends_on=db:service_healthy:false,assets:service_completed_successfully:false

Naivni `split(",")` by z toho udelal nesmysl, proto to testy hlidaji.
Vsechno jsou to ciste funkce - Docker se tady nevola.
"""

import unittest

from sysmon_app.collectors.docker import OTHER_PROJECT, group_by_project, parse_labels


def fake_container(names, labels=None, **extra):
    """Kontejner zhruba tak, jak ho vraci `docker ps --format '{{json .}}'`."""
    container = {"Names": names, "ID": (names * 12)[:12], "Image": "img:latest"}
    if labels is not None:
        container["Labels"] = labels
    container.update(extra)
    return container


class ParseLabelsTest(unittest.TestCase):
    def test_parses_key_value_pairs(self):
        self.assertEqual(parse_labels("a=1,b=2"), {"a": "1", "b": "2"})

    def test_empty_value_is_kept(self):
        self.assertEqual(parse_labels("com.docker.compose.depends_on=,b=2"),
                         {"com.docker.compose.depends_on": "", "b": "2"})

    def test_value_may_contain_comma(self):
        """Skutecny pripad z `docker ps`: depends_on ma v hodnote carku."""
        raw = ("com.docker.compose.depends_on=db:service_healthy:false,"
               "assets:service_completed_successfully:false,"
               "com.docker.compose.project=gym,com.docker.compose.service=app")
        labels = parse_labels(raw)
        self.assertEqual(
            labels["com.docker.compose.depends_on"],
            "db:service_healthy:false,assets:service_completed_successfully:false",
        )
        self.assertEqual(labels["com.docker.compose.project"], "gym")
        self.assertEqual(labels["com.docker.compose.service"], "app")

    def test_value_may_contain_equals_and_spaces(self):
        raw = "com.docker.compose.version=5.6.0,maintainer=NGINX Docker Maintainers <x@y>"
        labels = parse_labels(raw)
        self.assertEqual(labels["com.docker.compose.version"], "5.6.0")
        self.assertEqual(labels["maintainer"], "NGINX Docker Maintainers <x@y>")

    def test_absent_labels(self):
        self.assertEqual(parse_labels(""), {})
        self.assertEqual(parse_labels(None), {})


class GroupByProjectTest(unittest.TestCase):
    def test_groups_by_project_label(self):
        shop = fake_container("shop-web-1", "com.docker.compose.project=shop")
        blog = fake_container("blog-web-1", "com.docker.compose.project=blog")
        out = group_by_project([shop, blog, fake_container(
            "shop-db-1", "com.docker.compose.project=shop")])
        self.assertEqual(sorted(out), ["blog", "shop"])
        self.assertEqual([c["Names"] for c in out["shop"]],
                         ["shop-db-1", "shop-web-1"])

    def test_container_without_label_goes_to_other(self):
        out = group_by_project([fake_container("nginx", "maintainer=NGINX")])
        self.assertEqual(list(out), [OTHER_PROJECT])

    def test_container_without_labels_field_at_all_goes_to_other(self):
        out = group_by_project([fake_container("nginx")])
        self.assertEqual(list(out), [OTHER_PROJECT])

    def test_empty_project_label_goes_to_other(self):
        out = group_by_project([fake_container("nginx", "com.docker.compose.project=")])
        self.assertEqual(list(out), [OTHER_PROJECT])

    def test_other_group_is_last_and_rest_is_alphabetical(self):
        containers = [
            fake_container("z-1", "com.docker.compose.project=zeta"),
            fake_container("o-1", None),
            fake_container("a-1", "com.docker.compose.project=alfa"),
        ]
        self.assertEqual(list(group_by_project(containers)),
                         ["alfa", "zeta", OTHER_PROJECT])

    def test_containers_within_group_are_sorted_by_name(self):
        containers = [
            fake_container("c-1", "com.docker.compose.project=p"),
            fake_container("a-1", "com.docker.compose.project=p"),
            fake_container("b-1", "com.docker.compose.project=p"),
        ]
        out = group_by_project(containers)
        self.assertEqual([c["Names"] for c in out["p"]], ["a-1", "b-1", "c-1"])

    def test_keeps_every_container_field_untouched(self):
        """Seskupeni nesmi zahodit ani prepsat nic, co Docker poslal."""
        c = fake_container("app-1", "com.docker.compose.project=shop",
                           cpu="1.5%", memory="10MiB / 1GiB",
                           memory_percent="0.98%", Ports="0.0.0.0:8080->80/tcp",
                           State="running", Status="Up 3 hours")
        out = group_by_project([c])
        self.assertEqual(out["shop"], [c])

    def test_no_containers_is_empty_dict(self):
        self.assertEqual(group_by_project([]), {})


if __name__ == "__main__":
    unittest.main()
