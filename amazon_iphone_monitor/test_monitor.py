import unittest
from unittest.mock import patch
import monitor


def page(title='Apple iPhone 18 Pro Max 256GB Burgundy', stock='In stock', button='<input id="add-to-cart-button">', extra=''):
    return f'<span id="productTitle">{title}</span><div id="availability">{stock}</div>{button}{extra}'


class DetectionTests(unittest.TestCase):
    def test_discovery_rejects_accessories_even_with_empty_heading(self):
        html = '<div data-component-type="s-search-result" data-asin="B012345678"><h2></h2><span>Case for iPhone 18 Pro Max Burgundy</span></div>'
        self.assertEqual(monitor.discover(html), [])

    def test_available(self):
        self.assertEqual(monitor.classify(page())['status'], 'available')

    def test_out_of_stock_beats_button(self):
        self.assertEqual(monitor.classify(page(stock='Currently unavailable'))['status'], 'unavailable')

    def test_accessory_and_wrong_model(self):
        for title in ['Case for iPhone 18 Pro Max Burgundy', 'Sleeve for iPhone 18 Pro Max Burgundy', 'Apple iPhone 18 Pro Burgundy', 'Apple iPhone 17 Pro Max Burgundy']:
            self.assertEqual(monitor.classify(page(title=title))['status'], 'mismatch')

    def test_selected_colour_overrides_title(self):
        self.assertEqual(monitor.classify(page(extra='<div id="variation_color_name"><span class="selection">Black</span></div>'))['status'], 'mismatch')

    def test_disabled_and_hidden_buttons(self):
        for button in ['', '<input id="add-to-cart-button" disabled>', '<div class="aok-hidden"><input id="add-to-cart-button"></div>']:
            self.assertEqual(monitor.classify(page(button=button))['status'], 'unknown')

    def test_no_stock_claim(self):
        self.assertEqual(monitor.classify(page(stock='See all buying options'))['status'], 'unknown')

    def test_blocked_and_broken(self):
        for html in ['<input id="captchacharacters">', '<html>Service unavailable</html>']:
            with self.assertRaises(RuntimeError):
                monitor.classify(html)

    def test_seller_required(self):
        self.assertEqual(monitor.classify(page(), True)['status'], 'unknown')

    @patch('monitor.time.sleep')
    @patch('monitor.save_json')
    @patch('monitor.email')
    @patch('monitor.fetch')
    def test_alert_transitions_and_failed_send(self, fetch, send, save, sleep):
        config = {'search': False, 'product_urls': ['https://www.amazon.co.uk/dp/B012345678']}
        state = {}
        fetch.return_value = page()
        send.side_effect = RuntimeError('mail failure')
        self.assertEqual(monitor.cycle(config, state, 'secret'), 1)
        send.side_effect = None
        monitor.cycle(config, state, 'secret')
        monitor.cycle(config, state, 'secret')
        self.assertEqual(send.call_count, 2)
        fetch.return_value = page(stock='Unknown')
        monitor.cycle(config, state, 'secret')
        fetch.return_value = page()
        monitor.cycle(config, state, 'secret')
        self.assertEqual(send.call_count, 2)
        fetch.return_value = page(stock='Currently unavailable')
        monitor.cycle(config, state, 'secret')
        fetch.return_value = page()
        monitor.cycle(config, state, 'secret')
        self.assertEqual(send.call_count, 3)

    @patch('monitor.time.sleep')
    @patch('monitor.save_json')
    @patch('monitor.fetch')
    def test_stale_discovered_mismatch_is_pruned(self, fetch, save, sleep):
        config = {'search': False, 'product_urls': []}
        state = {'known_asins': ['B012345678'], 'products': {'B012345678': {'status': 'unknown'}}}
        fetch.return_value = page(title='Apple iPhone 18 Pro Max 256GB Glacier')
        self.assertEqual(monitor.cycle(config, state, '', False), 0)
        self.assertEqual(state['known_asins'], [])
        self.assertNotIn('B012345678', state['products'])


if __name__ == '__main__':
    unittest.main()
