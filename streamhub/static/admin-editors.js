/* Admin page editors (admins only): the hub's JSON files (apps and boards, users, news, settings), Docker
 * (daemon, containers, images) and the static files of the cdf folder.
 *
 * Each change saves the whole file through /api/admin/files/<key>, which validates it like `streamhub check`,
 * refuses it with 409 when the file changed since it was loaded, hashes new passwords and writes atomically.
 * A saved config file is applied at once. Only the fields a user changed are written, so keys the forms don't
 * know are kept. Uses the helpers that admin.html exposes as window.shAdmin.
 */
(function () {
	"use strict";
	var A = window.shAdmin, el = A.el, clear = A.clear;
	// From the hub: reserved app IDs, every option list with its labels, and the forms of the settings' JSON objects.
	var META = JSON.parse(document.getElementById("admin-meta").textContent);
	var CHOICES = META.choices;
	var PASSWORD_MASK = "********";  // what the server shows instead of a stored password
	var IMAGE_FILE = /\.(png|jpe?g|gif|svg|webp|ico|bmp)$/i;

	function $(id) { return document.getElementById(id); }
	function copy(value) { return JSON.parse(JSON.stringify(value)); }
	function str(value) { return value === undefined || value === null ? "" : String(value); }
	function asList(value) { return Array.isArray(value) ? value.slice() : value === undefined || value === null ? [] : [value]; }
	function isObject(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
	function lines(text) { return text.split("\n").map(function (x) { return x.trim(); }).filter(Boolean); }
	function fail(message) { throw new Error(message); }

	// -- files: loaded when their tab opens, saved whole --
	var files = {};
	function load(key) {
		return A.api("GET", "/api/admin/files/" + key).then(function (r) {
			var file = {version: r.version, exists: r.exists, path: r.path, error: r.error || "", data: null};
			if (!file.error && r.text.trim()) {
				try { file.data = JSON.parse(r.text); } catch (e) { file.error = "The file is not valid JSON (" + e.message + "). Fix it in JSON files."; }
			}
			files[key] = file;
			return file;
		});
	}
	function save(key, data) {
		var text = JSON.stringify(data, null, "\t") + "\n";
		return A.api("POST", "/api/admin/files/" + key, {text: text, version: files[key].version}).then(function (r) {
			if (!r.saved) { fail(r.error); }
			return r;
		});
	}
	// Save, tell the user, and show the file again (users: so a new password is replaced by the mask).
	function saveAndShow(key, data, view) {
		return save(key, data).then(function (r) {
			A.toast(r.message);
			view();
			return r;
		});
	}

	// -- suggestions for text fields: <datalist> elements, filled once --
	var datalists = {};
	function datalist(id, values) {
		if (!datalists[id]) {
			datalists[id] = el("datalist");
			datalists[id].id = id;
			document.body.appendChild(datalists[id]);
		}
		if (values) {
			clear(datalists[id]);
			values.forEach(function (v) {
				var option = el("option", Array.isArray(v) ? v[1] : null);
				option.value = Array.isArray(v) ? v[0] : v;
				datalists[id].appendChild(option);
			});
		}
		return id;
	}
	datalist("timezone-list", META.timezones);
	var environments = null;  // the conda envs of the server, asked once
	function environmentList() {
		if (!environments) {
			environments = A.api("GET", "/api/admin/environments").then(function (r) {
				datalist("environment-list", r.environments.map(function (e) { return [e.name, e.path]; }));
			}).catch(function () {});
		}
		return datalist("environment-list");
	}
	// A live verdict on a path of the server: relative paths start at `base` (relative to the config folder).
	function pathCheck(value, base) {
		if (!value.trim()) { return ["", ""]; }
		var url = "/api/admin/path-check?path=" + encodeURIComponent(value.trim()) + "&base=" + encodeURIComponent(base || "");
		return A.api("GET", url).then(function (r) {
			return r.exists ? ["ok", "Found on the server: " + r.path] : ["", "Not on the server (yet): " + r.path];
		}, function () { return ["", ""]; });
	}
	// The images of the cdf folder, listed once per page.
	var cdfImages = null;
	function listImages(refresh) {
		if (!cdfImages || refresh) {
			cdfImages = A.api("GET", "/api/admin/cdf").then(function (r) {
				return r.entries.filter(function (e) { return !e.dir && IMAGE_FILE.test(e.path); }).map(function (e) { return e.path; });
			});
		}
		return cdfImages;
	}
	function choiceOptions(name, empty) {
		var options = (CHOICES[name] || []).map(function (o) { return [o[0], o[1]]; });
		return empty === undefined ? options : [["", empty]].concat(options);
	}
	function randomPassword() {
		var alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789", bytes = new Uint8Array(16), out = "";
		window.crypto.getRandomValues(bytes);
		bytes.forEach(function (b) { out += alphabet.charAt(b % alphabet.length); });
		return out;
	}

	// -- form fields: {name, label, type, value, options, placeholder, help, when, wide, ...} --
	// Types: section, checkbox, checks, select, textarea, image, schedule, subform, rows, and input types (text, number,
	// password). Extras: badge, mono, readonly, list (a datalist id), check(value) -> [ok|bad|"", message] or a promise of
	// it, describe(value) -> help for the current value, generate (a "Generate" button for passwords).
	function buildField(spec) {
		if (spec.type === "section") { return {spec: spec, node: el("h3", spec.label, "sh-form-section")}; }
		if (spec.type === "subform") { return buildSubform(spec); }
		if (spec.type === "rows") { return buildRows(spec); }
		var node = el("div", null, "sh-field" + (spec.wide ? " sh-field-wide" : "")), input, get, id = "f-" + spec.name;
		if (spec.type === "checkbox") {
			var check = el("label", null, "sh-check");
			input = el("input");
			input.type = "checkbox";
			input.id = id;
			input.checked = !!spec.value;
			check.appendChild(input);
			check.appendChild(el("span", spec.label));
			node.appendChild(check);
			get = function () { return input.checked; };
		} else if (spec.type === "checks") {
			node.appendChild(el("span", spec.label, "sh-field-label"));
			var list = el("div", null, "sh-checks"), boxes = [];
			spec.options.forEach(function (option) {
				var item = el("label", null, "sh-check"), box = el("input");
				box.type = "checkbox";
				box.value = option[0];
				box.checked = spec.value.indexOf(option[0]) !== -1;
				boxes.push(box);
				item.appendChild(box);
				item.appendChild(el("span", option[1]));
				list.appendChild(item);
			});
			node.appendChild(list);
			get = function () { return boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; }); };
		} else {
			var label = el("label", spec.label, "sh-field-label");
			label.htmlFor = id;
			(Array.isArray(spec.badge) ? spec.badge : spec.badge ? [spec.badge] : []).forEach(function (badge) {
				label.appendChild(el("span", badge, "sh-chip sh-chip-muted"));
			});
			node.appendChild(label);
			if (spec.type === "select") {
				input = el("select");
				spec.options.forEach(function (option) {
					var item = el("option", option[1]);
					item.value = option[0];
					input.appendChild(item);
				});
			} else if (spec.type === "textarea") {
				input = el("textarea");
				input.rows = spec.rows || 3;
			} else {
				input = el("input");
				input.type = spec.type === "image" ? "text" : spec.type === "schedule" ? "time" : spec.type || "text";
				input.autocomplete = spec.type === "password" ? "new-password" : "off";
			}
			input.id = id;
			input.className = "form-control form-control-sm" + (spec.mono ? " sh-mono" : "");
			input.value = spec.type === "schedule" && spec.value === "off" ? "" : str(spec.value);
			input.spellcheck = false;
			if (spec.placeholder) { input.placeholder = spec.placeholder; }
			if (spec.readonly) { input.readOnly = true; }
			if (spec.list) { input.setAttribute("list", spec.list); }
			get = function () { return input.value; };
			if (spec.type === "image" || spec.type === "schedule" || spec.generate) {
				var row = el("div", null, "sh-input-row");
				row.appendChild(input);
				node.appendChild(row);
				if (spec.type === "image") { addImagePicker(node, row, input, spec); }
				if (spec.type === "schedule") {  // a time, or off; empty means the default time
					var off = el("label", null, "sh-check"), box = el("input");
					box.type = "checkbox";
					box.checked = spec.value === "off";
					input.disabled = box.checked;
					off.appendChild(box);
					off.appendChild(el("span", "Off"));
					row.appendChild(off);
					box.addEventListener("change", function () { input.disabled = box.checked; });
					get = function () { return box.checked ? "off" : input.value; };
				}
				if (spec.generate) {
					var generate = el("button", "Generate", "btn btn-sm sh-btn-quiet");
					generate.type = "button";
					generate.addEventListener("click", function () {
						input.type = "text";  // shown once, so it can be copied and handed over
						input.value = randomPassword();
						input.dispatchEvent(new Event("input", {bubbles: true}));
						input.select();
					});
					row.appendChild(generate);
				}
			} else {
				node.appendChild(input);
			}
		}
		if (spec.check) {  // a live verdict on the value, such as whether an app ID is free or a folder exists
			var verdict = el("small", null, "sh-field-check"), asked = 0, timer = null;
			verdict.setAttribute("aria-live", "polite");
			var show = function (result) {
				verdict.textContent = result[1];
				verdict.className = "sh-field-check" + (result[0] ? " is-" + result[0] : "");
			};
			var update = function () {
				var result = spec.check(input.value), ticket = ++asked;
				if (result && typeof result.then === "function") {
					result.then(function (r) { if (ticket === asked) { show(r); } });
				} else {
					show(result);
				}
			};
			input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(update, 250); });
			node.appendChild(verdict);
			setTimeout(update);  // once the other fields exist
			node.addEventListener("sh-recheck", update);
		}
		if (spec.help || spec.key || spec.describe) {
			var help = el("small", null, "sh-field-help"), text = document.createTextNode("");
			if (spec.key) { help.appendChild(el("code", spec.key)); }
			help.appendChild(text);
			var describe = function () {
				var words = spec.describe ? spec.describe(get()) : spec.help;
				text.textContent = (spec.key && words ? " · " : "") + (words || "");
			};
			describe();
			if (spec.describe) { node.addEventListener("change", describe); }
			node.appendChild(help);
		}
		var field = {spec: spec, node: node, get: get, input: input};
		field.initial = JSON.stringify(get());
		field.changed = function () { return !node.hidden && JSON.stringify(get()) !== field.initial; };
		return field;
	}

	// A "Choose" button that opens a grid of the cdf folder's images, and an "Upload" button that adds one.
	function addImagePicker(node, row, input, spec) {
		var choose = el("button", null, "btn btn-sm sh-btn-quiet"), uploadButton = el("label", null, "btn btn-sm sh-btn-quiet mb-0");
		var file = el("input"), grid = el("div", null, "sh-picker"), preview = el("img", null, "sh-thumb");
		choose.type = "button";
		choose.appendChild(el("i", null, "fa fa-picture-o"));
		choose.appendChild(document.createTextNode(" Choose"));
		uploadButton.appendChild(el("i", null, "fa fa-upload"));
		uploadButton.appendChild(document.createTextNode(" Upload"));
		file.type = "file";
		file.accept = "image/*";
		file.hidden = true;
		uploadButton.appendChild(file);
		preview.alt = "";
		row.insertBefore(preview, input);
		row.appendChild(choose);
		row.appendChild(uploadButton);
		grid.hidden = true;
		node.appendChild(grid);
		function showPreview() { preview.hidden = !input.value.trim(); if (input.value.trim()) { preview.src = input.value.trim(); } }
		function pick(url) {
			input.value = url;
			input.dispatchEvent(new Event("input", {bubbles: true}));
			showPreview();
			grid.hidden = true;
		}
		function fill(paths) {
			clear(grid);
			if (!paths.length) { grid.appendChild(el("span", "No images yet: upload one.", "sh-muted small")); }
			paths.forEach(function (path) {
				var url = cdfUrl(path), button = el("button", null, url === input.value.trim() ? "is-current" : ""), img = el("img");
				button.type = "button";
				button.title = url;
				img.src = url;
				img.alt = "";
				img.loading = "lazy";
				button.appendChild(img);
				button.appendChild(el("span", nameOf(path)));
				button.addEventListener("click", function () { pick(url); });
				grid.appendChild(button);
			});
		}
		choose.addEventListener("click", function () {
			if (!grid.hidden) { grid.hidden = true; return; }
			grid.hidden = false;
			clear(grid);
			grid.appendChild(el("span", "Loading…", "sh-muted small"));
			listImages().then(fill).catch(function (error) { clear(grid); grid.appendChild(el("span", error.message, "text-danger small")); });
		});
		file.addEventListener("change", function () {
			var chosen = file.files[0];
			file.value = "";
			if (!chosen) { return; }
			var form = new FormData(), folder = spec.uploadFolder || "";
			form.append("files", chosen, chosen.name);
			A.toast("Uploading " + chosen.name + "…");
			fetch("/api/admin/cdf/upload?folder=" + encodeURIComponent(folder) + "&overwrite=1", {
				method: "POST", body: form, credentials: "same-origin", headers: {"X-XSRFToken": XSRF}
			}).then(function (response) { return response.json(); }).then(function (r) {
				if (!r.ok) { A.toast(r.error, true); return; }
				A.toast("Uploaded " + chosen.name);
				listImages(true);
				pick(cdfUrl(join(folder, chosen.name)));
			}).catch(function () { A.toast("The upload failed.", true); });
		});
		input.addEventListener("change", showPreview);
		showPreview();
	}

	// -- forms for JSON objects (SUBFORMS of the hub): fields for the known keys; others are kept as they are --
	// A field of a sub-form, from the hub's (key, kind, label, placeholder, help, when).
	function subSpec(sub, prefix, value, boards) {
		var kind = sub.kind.split(":")[0], list = sub.kind.split(":")[1], v = value[sub.key];
		var spec = {name: prefix + "-" + sub.key, key: sub.key, label: sub.label, placeholder: sub.placeholder, help: sub.help};
		if (kind === "bool") {
			spec.type = "checkbox";
			spec.value = v === true;
		} else if (kind === "tristate") {
			spec.type = "select";
			spec.value = v === true ? "true" : v === false ? "false" : "";
			spec.options = [["", "Default (" + sub.placeholder + ")"], ["true", "On"], ["false", "Off"]];
		} else if (kind === "choice") {
			spec.type = "select";
			spec.value = str(v);
			spec.options = choiceOptions(list, sub.placeholder ? "Default (" + sub.placeholder + ")" : "Choose…");
		} else if (kind === "checks" || kind === "boards") {
			spec.type = "checks";
			spec.wide = true;
			spec.value = asList(v);
			spec.options = kind === "boards" ? boards : choiceOptions(list);
			spec.value.forEach(function (x) { if (!spec.options.some(function (o) { return o[0] === x; })) { spec.options.push([x, x]); } });
		} else if (kind === "json") {
			spec.type = "textarea";
			spec.rows = 2;
			spec.mono = true;
			spec.wide = true;
			spec.value = v === undefined || v === null ? "" : JSON.stringify(v);
		} else if (kind === "strings") {
			spec.value = asList(v).join(", ");
		} else {
			spec.type = kind === "int" ? "number" : "text";
			spec.value = str(v);
		}
		return spec;
	}
	// Writes a sub-form field's value into `target`; an empty value removes the key. Throws on bad input.
	function subPut(sub, target, raw) {
		var kind = sub.kind.split(":")[0];
		if (kind === "bool") { if (raw) { target[sub.key] = true; } else { delete target[sub.key]; } return; }
		if (kind === "tristate") { put(target, sub.key, raw === "" ? "" : raw === "true"); return; }
		if (kind === "checks" || kind === "boards") { put(target, sub.key, raw); return; }
		raw = raw.trim();
		if (kind === "int") { put(target, sub.key, raw === "" ? "" : parseInteger(raw, sub.label)); return; }
		if (kind === "strings") { put(target, sub.key, raw.split(/\s*,\s*/).filter(Boolean)); return; }
		if (kind === "json") { put(target, sub.key, raw === "" ? "" : parseJson(raw, sub.label, /^\s*\[/.test(raw) ? "list" : "object")); return; }
		put(target, sub.key, raw);
	}
	function whenOf(sub) {
		if (!sub.when) { return null; }
		var at = sub.when.indexOf(":"), key = sub.when.slice(0, at), values = sub.when.slice(at + 1).split(",");
		return function (current) { return values.indexOf(current[key]) !== -1; };
	}
	// One object: a grid of fields. read() returns the object, or throws a message on bad input.
	function subGrid(form, prefix, value, boards) {
		var grid = el("div", null, "sh-form-grid"), parts = [];
		form.forEach(function (sub) {
			var built = buildField(subSpec(sub, prefix, value, boards));
			built.sub = sub;
			built.when = whenOf(sub);
			grid.appendChild(built.node);
			parts.push(built);
		});
		function current() {
			var values = {};
			parts.forEach(function (p) { values[p.sub.key] = p.get(); });
			return values;
		}
		function refresh() { var values = current(); parts.forEach(function (p) { if (p.when) { p.node.hidden = !p.when(values); } }); }
		grid.addEventListener("input", refresh);
		grid.addEventListener("change", refresh);
		refresh();
		return {node: grid, read: function () {
			var result = copy(value);  // keys the form doesn't know stay
			parts.forEach(function (p) { if (!p.node.hidden) { subPut(p.sub, result, p.get()); } else { delete result[p.sub.key]; } });
			return result;
		}};
	}
	// A field whose value is a JSON object or list edited with a form, or as JSON text ("Edit as JSON").
	function jsonField(spec, render, emptyValue) {
		var node = el("div", null, "sh-field sh-field-wide"), label = el("span", spec.label, "sh-field-label");
		(Array.isArray(spec.badge) ? spec.badge : spec.badge ? [spec.badge] : []).forEach(function (badge) {
			label.appendChild(el("span", badge, "sh-chip sh-chip-muted"));
		});
		node.appendChild(label);
		if (spec.help || spec.key) {  // above the form, which can be long
			var help = el("small", null, "sh-field-help");
			if (spec.key) { help.appendChild(el("code", spec.key)); }
			if (spec.help) { help.appendChild(document.createTextNode((spec.key ? " · " : "") + spec.help)); }
			node.appendChild(help);
		}
		var box = el("div", null, "sh-subform"), bar = el("div", null, "sh-subform-bar"), toggle = el("button", "Edit as JSON", "btn btn-sm sh-btn-quiet");
		toggle.type = "button";
		bar.appendChild(toggle);
		box.appendChild(bar);
		var body = el("div"), text = el("textarea", null, "form-control form-control-sm sh-mono");
		text.rows = 6;
		text.spellcheck = false;
		text.hidden = true;
		box.appendChild(body);
		box.appendChild(text);
		node.appendChild(box);
		var value = spec.value === undefined || spec.value === null || spec.value === "" ? emptyValue : copy(spec.value), view = null;
		function draw() { clear(body); view = render(body, value); }
		draw();
		var asJson = false;
		toggle.addEventListener("click", function () {
			if (!asJson) {
				try { value = view.read(); } catch (error) { A.toast(error.message, true); return; }
				text.value = JSON.stringify(value, null, 2);
			} else {
				try { value = parseJson(text.value.trim() || JSON.stringify(emptyValue), spec.label, Array.isArray(emptyValue) ? "list" : "object"); }
				catch (error) { A.toast(error.message, true); return; }
				draw();
			}
			asJson = !asJson;
			text.hidden = !asJson;
			body.hidden = asJson;
			toggle.textContent = asJson ? "Edit with the form" : "Edit as JSON";
			node.dispatchEvent(new Event("change", {bubbles: true}));
		});
		// The value, or a description of bad input (validate() throws it at save time).
		function get() {
			try {
				return asJson ? parseJson(text.value.trim() || JSON.stringify(emptyValue), spec.label, Array.isArray(emptyValue) ? "list" : "object") : view.read();
			} catch (error) { return {"$invalid": error.message}; }
		}
		var field = {spec: spec, node: node, get: get};
		field.initial = JSON.stringify(get());
		field.changed = function () { return !node.hidden && JSON.stringify(get()) !== field.initial; };
		field.validate = function () { var v = get(); if (isObject(v) && v.$invalid) { fail(v.$invalid); } };
		return field;
	}
	function buildSubform(spec) {
		return jsonField(spec, function (body, value) {
			var grid = subGrid(spec.form, spec.name, isObject(value) ? value : {}, spec.boards || []);
			body.appendChild(grid.node);
			return grid;
		}, {});
	}
	function buildRows(spec) {
		return jsonField(spec, function (body, value) {
			var rows = [], list = el("div", null, "sh-rows"), add = el("button", null, "btn btn-sm sh-btn-quiet");
			function addRow(item) {
				var card = el("div", null, "sh-row-card"), grid = subGrid(spec.form, spec.name + "-" + rows.length, isObject(item) ? item : {}, spec.boards || []);
				var remove = el("button", null, "sh-icon-btn is-bad"), row = {card: card, grid: grid};
				remove.type = "button";
				remove.title = "Remove";
				remove.setAttribute("aria-label", "Remove");
				remove.appendChild(el("i", null, "fa fa-trash"));
				remove.addEventListener("click", function () {
					rows.splice(rows.indexOf(row), 1);
					list.removeChild(card);
					list.dispatchEvent(new Event("change", {bubbles: true}));
				});
				card.appendChild(remove);
				card.appendChild(grid.node);
				list.appendChild(card);
				rows.push(row);
			}
			(Array.isArray(value) ? value : []).forEach(addRow);
			add.type = "button";
			add.appendChild(el("i", null, "fa fa-plus"));
			add.appendChild(document.createTextNode(" " + (spec.addLabel || "Add")));
			add.addEventListener("click", function () { addRow({}); list.dispatchEvent(new Event("change", {bubbles: true})); });
			body.appendChild(list);
			body.appendChild(add);
			return {read: function () { return rows.map(function (r) { return r.grid.read(); }); }};
		}, []);
	}

	// -- the editor dialog: onSave(values, changed) saves and returns a promise, or throws a message --
	var editor = null;
	function openEditor(title, specs, onSave) {
		var box = $("editor-fields");
		clear(box);
		var grid = el("div", null, "sh-form-grid");
		box.appendChild(grid);
		var fields = specs.map(function (spec) { var field = buildField(spec); grid.appendChild(field.node); return field; });
		function values() {
			var result = {};
			fields.forEach(function (f) { if (f.get) { result[f.spec.name] = f.get(); } });
			return result;
		}
		function refresh(event) {
			var current = values();
			fields.forEach(function (f) { if (f.spec.when) { f.node.hidden = !f.spec.when(current); } });
			if (event && event.target && (event.target.id === "f-type" || event.target.id === "f-folder")) {
				fields.forEach(function (f) { if (f.spec.check) { f.node.dispatchEvent(new Event("sh-recheck")); } });
			}
		}
		grid.addEventListener("input", refresh);
		grid.addEventListener("change", refresh);
		refresh();
		editor = {fields: fields, values: values, onSave: onSave};
		$("editor-title").textContent = title;
		$("editor-error").hidden = true;
		A.openModal("editor-box");
		var first = fields.filter(function (f) { return f.input && !f.input.readOnly; })[0];
		if (first) { first.input.focus(); }
	}
	function editorError(message) {
		$("editor-error").textContent = message;
		$("editor-error").hidden = false;
	}
	$("editor-form").addEventListener("submit", function (event) {
		event.preventDefault();
		if (!editor) { return; }
		var byName = {};
		editor.fields.forEach(function (f) { if (f.spec.name) { byName[f.spec.name] = f; } });
		var changed = function (name) { return byName[name] ? byName[name].changed() : false; };
		var button = this.querySelector("[type=submit]");
		var result;
		$("editor-error").hidden = true;
		try {
			editor.fields.forEach(function (f) { if (f.validate && f.changed()) { f.validate(); } });
			result = editor.onSave(editor.values(), changed);
		} catch (error) { editorError(error.message); return; }
		button.disabled = true;
		Promise.resolve(result)
			.then(function () { editor = null; A.closeModal("editor-box"); })
			.catch(function (error) { editorError(error.message); })
			.then(function () { button.disabled = false; });
	});
	Array.prototype.forEach.call(document.querySelectorAll("#editor-box [data-close]"), function (button) {
		button.addEventListener("click", function () { A.closeModal("editor-box"); });
	});

	// -- table helpers --
	function table(headings) {
		var node = el("table", null, "sh-table sh-table-stack"), thead = el("thead"), row = el("tr"), body = el("tbody");
		headings.forEach(function (h) { row.appendChild(el("th", h, h ? "" : "text-right")); });
		thead.appendChild(row);
		node.appendChild(thead);
		node.appendChild(body);
		return {node: node, body: body};
	}
	function cell(row, label, content, className) {
		var td = el("td", null, className);
		td.setAttribute("data-label", label);
		if (content instanceof Node) { td.appendChild(content); } else { td.textContent = content; }
		row.appendChild(td);
		return td;
	}
	function actions(buttons) {
		var box = el("div", null, "sh-row-actions");
		buttons.forEach(function (b) {
			var button = el("button", null, "sh-icon-btn " + (b[2] || ""));
			button.type = "button";
			button.title = b[1];
			button.setAttribute("aria-label", b[1]);
			button.appendChild(el("i", null, "fa " + b[0]));
			button.addEventListener("click", b[3]);
			box.appendChild(button);
		});
		return box;
	}
	// A grip that reorders: drag it (mouse, pen or touch), or focus it and press Up or Down.
	function dragHandle(kind, label) {
		var grip = el("button", null, "sh-drag");
		grip.type = "button";
		grip.setAttribute("data-drag", kind);
		grip.title = "Drag to reorder (or focus and press Up or Down)";
		grip.setAttribute("aria-label", "Move " + label + ": drag, or press Up or Down");
		grip.appendChild(el("i", null, "fa fa-bars"));
		return grip;
	}
	// Reorders the direct children of `container` that match `items` (each with a data-key) by their
	// [data-drag=<kind>] grip. onOrder(keys) saves the new order of every item.
	function sortable(container, items, kind, onOrder) {
		function list() { return Array.prototype.filter.call(container.children, function (n) { return n.matches(items); }); }
		function keys() { return list().map(function (n) { return n.getAttribute("data-key"); }); }
		function itemOf(target) {
			var grip = target.closest("[data-drag=" + kind + "]"), item = grip && grip.closest(items);
			return item && item.parentNode === container ? item : null;
		}
		container.addEventListener("pointerdown", function (event) {
			var item = itemOf(event.target);
			if (!item || event.button > 0) { return; }
			event.preventDefault();
			// Followed on the document: moving the row in the DOM ends a pointer capture on its grip.
			var before = keys().join("\n"), pointer = event.pointerId;
			item.classList.add("is-dragging");
			function move(e) {
				if (e.pointerId !== pointer) { return; }
				var over = document.elementFromPoint(e.clientX, e.clientY), target = over && over.closest(items);
				if (!target || target === item || target.parentNode !== container) { return; }
				var box = target.getBoundingClientRect();
				container.insertBefore(item, e.clientY > box.top + box.height / 2 ? target.nextSibling : target);
			}
			function end(e) {
				if (e.pointerId !== pointer) { return; }
				document.removeEventListener("pointermove", move);
				document.removeEventListener("pointerup", end);
				document.removeEventListener("pointercancel", end);
				item.classList.remove("is-dragging");
				if (keys().join("\n") !== before) { onOrder(keys()); }
			}
			document.addEventListener("pointermove", move);
			document.addEventListener("pointerup", end);
			document.addEventListener("pointercancel", end);
		});
		container.addEventListener("keydown", function (event) {
			var item = itemOf(event.target);
			if (!item || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) { return; }
			event.preventDefault();
			var all = list(), at = all.indexOf(item), to = at + (event.key === "ArrowUp" ? -1 : 1);
			if (to < 0 || to >= all.length) { return; }
			container.insertBefore(item, event.key === "ArrowUp" ? all[to] : all[to].nextSibling);
			onOrder(keys(), item.getAttribute("data-key"));
		});
	}
	// `entries` reordered to follow `keys` (by keyOf); entries without a key stay at the end.
	function ordered(entries, keys, keyOf) {
		var keyed = {}, rest = [];
		entries.forEach(function (e) { var k = keyOf(e); if (k === null) { rest.push(e); } else { keyed[k] = e; } });
		return keys.map(function (k) { return keyed[k]; }).filter(Boolean).concat(rest);
	}
	function chips(values, empty) {
		var box = el("div", null, "sh-chips");
		if (!values.length) { box.appendChild(el("span", empty, "sh-muted")); }
		values.forEach(function (v) { box.appendChild(el("span", v, "sh-chip sh-chip-muted")); });
		return box;
	}
	function showError(box, message) {
		clear(box);
		box.appendChild(el("div", message, "sh-alert sh-alert-bad"));
	}
	function confirmed(message, action) {
		if (window.confirm(message)) {
			Promise.resolve().then(action).catch(function (error) { A.toast(error.message, true); });
		}
	}

	// -- apps and boards --
	var APP_TYPES = META.appTypes.map(function (t) { return [t[0], t[1]]; });
	var TYPE_HELP = {builtin: "A tool that comes with Streamhub"};
	META.appTypes.forEach(function (t) { TYPE_HELP[t[0]] = t[2]; });
	var TYPE_LABELS = {streamlit: "Streamlit", python: "Python", docker: "Docker", kubernetes: "Kubernetes", url: "Link", curl: "Proxy",
		page: "Hub page", builtin: "Built-in"};
	var SUFFIX_TYPES = {sl: "streamlit", py: "python", url: "url", curl: "curl", cmd: "builtin"};
	// An entry's type as the hub reads it: `type`, else (files from before 2.2) the app ID suffix and `runtime`.
	function typeOf(entry) {
		if (entry.type) { return entry.type; }
		var match = /\.([^.]+)$/.exec(entry.app_id || ""), type = SUFFIX_TYPES[match ? match[1].toLowerCase() : ""] || "page";
		return (type === "streamlit" || type === "python") && entry.runtime && entry.runtime !== "process" ? entry.runtime : type;
	}
	function servesOf(entry) {
		if (entry.type) { return entry.serves || "web"; }
		return /\.sl$/i.test(entry.app_id || "") ? "streamlit" : "web";
	}
	function typeLabel(entry) {
		var type = typeOf(entry);
		return TYPE_LABELS[type] + ((type === "docker" || type === "kubernetes") && servesOf(entry) === "streamlit" ? " · Streamlit" : "");
	}
	// ["ok" | "bad" | "", message] for a new app ID: its characters, the hub's own paths, and the other apps.
	function idStatus(value, self) {
		var id = value.trim(), type = document.getElementById("f-type") ? document.getElementById("f-type").value : "";
		if (!id) { return ["", ""]; }
		if (id === self) { return ["ok", "The current ID: the app is at /" + id + "/"]; }
		if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(id)) { return ["bad", "Use letters, digits, '.', '_' and '-', starting with a letter or digit"]; }
		var reserved = META.reserved.indexOf(id.toLowerCase()) !== -1 || /\.brd$/i.test(id);
		if (reserved && type !== "page") { return ["bad", "Not available: the hub uses /" + id + "/ itself"]; }
		var other = allApps(appsData()).filter(function (a) { return a.app_id === id; })[0];
		if (other) { return ["bad", "Not available: " + (str(other.app_name) || other.app_id) + " uses it"]; }
		return ["ok", "Available: the app will be at /" + id + "/"];
	}
	function isApp(entry) { return isObject(entry) && typeof entry.app_id === "string"; }
	function appsData() {
		var data = files.apps.data;
		return Array.isArray(data) && isObject(data[0]) && Array.isArray(data[0].boards) ? data : null;
	}
	function boardsOf(data) { return data[0].boards.filter(isObject); }
	function topApps(data) { return data.slice(1).filter(isApp); }
	function allApps(data) {
		var result = [];
		topApps(data).forEach(function (app) {
			result.push(app);
			asList(app.children).filter(isApp).forEach(function (child) { result.push(child); });
		});
		return result;
	}
	// {list, index, entry, parent} of an app in `data`, or null.
	function findApp(data, appId) {
		for (var i = 1; i < data.length; i++) {
			var entry = data[i];
			if (!isApp(entry)) { continue; }
			if (entry.app_id === appId) { return {list: data, index: i, entry: entry, parent: null}; }
			var children = Array.isArray(entry.children) ? entry.children : [];
			for (var j = 0; j < children.length; j++) {
				if (isApp(children[j]) && children[j].app_id === appId) { return {list: children, index: j, entry: children[j], parent: entry}; }
			}
		}
		return null;
	}
	function emptyApps() { return [{boards: []}]; }

	function showApps() {
		return load("apps").then(renderApps).catch(function (error) { showError($("catalog"), error.message); });
	}
	// Saves a new order of boards or apps; moves made while a save runs are dropped (the list is redrawn).
	var reordering = false;
	function saveOrder(draft, what, focusKey) {
		if (reordering) { return; }
		reordering = true;
		save("apps", draft).then(function () {
			A.toast("Saved the new order of " + what + ".");
			return showApps();
		}).catch(function (error) {
			A.toast(error.message, true);
			return showApps();
		}).then(function () {
			reordering = false;
			var grip = focusKey && document.querySelector("[data-panel=apps] [data-key='" + CSS.escape(focusKey) + "'] [data-drag]");
			if (grip) { grip.focus(); }
		});
	}
	function renderApps() {
		var file = files.apps, boardsBox = $("boards"), appsBox = $("catalog");
		if (!file.data && !file.error) { file.data = emptyApps(); }
		var data = file.error ? null : appsData();
		$("board-add").disabled = $("app-add").disabled = !data;
		if (!data) {
			var message = file.error || "The apps file must be a list that starts with {\"boards\": [...]}. Fix it in JSON files.";
			showError(boardsBox, message);
			clear(appsBox);
			return;
		}
		// boards
		clear(boardsBox);
		var boards = table(["Board", "Label", "Access", "Apps", ""]);
		boardsOf(data).forEach(function (board) {
			var row = el("tr"), used = allApps(data).filter(function (a) { return asList(a.board).indexOf(board.name) !== -1; }).length;
			var name = el("div", null, "sh-drag-cell");
			name.appendChild(dragHandle("board", board.name));
			name.appendChild(el("span", board.name));
			row.setAttribute("data-key", board.name);
			cell(row, "Board", name, "sh-mono");
			cell(row, "Label", str(board.label || board.name));
			cell(row, "Access", el("span", board.auth ? "Login" : "Public", "sh-chip " + (board.auth ? "" : "sh-chip-muted")));
			cell(row, "Apps", String(used));
			cell(row, "", actions([
				["fa-pencil", "Edit", "", function () { editBoard(board.name); }],
				["fa-trash", "Delete", "is-bad", function () { deleteBoard(board.name, used); }]
			]), "text-right");
			boards.body.appendChild(row);
		});
		if (boardsOf(data).length) { boardsBox.appendChild(boards.node); } else { boardsBox.appendChild(el("p", "No boards yet.", "sh-muted")); }
		// The menu and the home page list boards in this order.
		sortable(boards.body, "tr", "board", function (keys, focusKey) {
			var draft = copy(data);
			draft[0].boards = ordered(draft[0].boards, keys, function (b) { return isObject(b) ? b.name : null; });
			saveOrder(draft, "boards", focusKey);
		});
		// apps, children under their parent: one <tbody> per top-level app, so an app moves with its children
		clear(appsBox);
		var query = $("catalog-search").value.trim().toLowerCase(), apps = table(["App", "Type", "Boards", "Display", ""]), shown = 0;
		apps.node.removeChild(apps.body);
		var block = null;
		function matches(app) { return (app.app_id + " " + str(app.app_name)).toLowerCase().indexOf(query) !== -1; }
		function appRow(app, parent) {
			var row = el("tr", null, parent ? "sh-child-row" : ""), name = el("div", null, "sh-app-cell sh-app-with-icon");
			if (!query) { name.appendChild(dragHandle(parent ? "child" : "app", app.app_id)); }  // filtered lists don't reorder
			if (parent) { row.setAttribute("data-key", app.app_id); }
			if (app.icon) { var icon = el("img", null, "sh-thumb"); icon.src = app.icon; icon.alt = ""; name.appendChild(icon); }
			var text = el("div");
			text.appendChild(el("b", str(app.app_name) || app.app_id));
			text.appendChild(el("small", (parent ? "↳ " : "") + app.app_id));
			name.appendChild(text);
			cell(row, "App", name);
			cell(row, "Type", el("span", typeLabel(app), "sh-chip"));
			cell(row, "Boards", chips(asList(app.board).map(function (b) { return b === "" ? "Home page" : b; }), "none"));
			cell(row, "Display", str(app.display || "show"));
			var buttons = [["fa-pencil", "Edit", "", function () { editApp(app.app_id, parent ? parent.app_id : ""); }]];
			if (!parent) { buttons.push(["fa-level-down", "Add a child app", "", function () { editApp(null, app.app_id); }]); }
			buttons.push(["fa-trash", "Delete", "is-bad", function () { deleteApp(app.app_id); }]);
			cell(row, "", actions(buttons), "text-right");
			block.appendChild(row);
			shown++;
		}
		topApps(data).forEach(function (app) {
			var children = asList(app.children).filter(isApp), hits = children.filter(matches);
			if (query && !matches(app) && !hits.length) { return; }
			block = el("tbody", null, "sh-app-block");
			block.setAttribute("data-key", app.app_id);
			apps.node.appendChild(block);
			appRow(app, null);
			(query && !matches(app) ? hits : children).forEach(function (child) { appRow(child, app); });
			if (!query) {  // a parent's children, in the order its card lists them
				sortable(block, "tr.sh-child-row", "child", function (keys, focusKey) {
					var draft = copy(data), parent = findApp(draft, app.app_id).entry;
					parent.children = ordered(asList(parent.children), keys, function (c) { return isApp(c) ? c.app_id : null; });
					saveOrder(draft, "the apps under " + (str(app.app_name) || app.app_id), focusKey);
				});
			}
		});
		appsBox.appendChild(shown ? apps.node : el("p", query ? "No app matches." : "No apps yet.", "sh-muted"));
		if (shown && !query) {  // boards list their apps in this order
			sortable(apps.node, "tbody.sh-app-block", "app", function (keys, focusKey) {
				var draft = copy(data);
				saveOrder([draft[0]].concat(ordered(draft.slice(1), keys, function (a) { return isApp(a) ? a.app_id : null; })),
					"apps", focusKey);
			});
		}
		$("catalog-order-hint").textContent = query ? "Clear the filter to reorder apps." :
			"Drag ☰ to change the order in which boards and apps appear (or focus it and press Up or Down).";
	}
	$("catalog-search").addEventListener("input", function () { if (files.apps) { renderApps(); } });

	function editBoard(name) {
		var data = appsData(), board = name ? boardsOf(data).filter(function (b) { return b.name === name; })[0] : {};
		openEditor(name ? "Board: " + name : "New board", [
			{name: "name", label: "Name", value: str(board.name), readonly: !!name, placeholder: "sales.brd",
				help: name ? "Fixed: users and apps refer to it" : "Unique, ends in .brd; the board's URL is /<name>/"},
			{name: "label", label: "Label", value: str(board.label), placeholder: "the name", help: "Menu text"},
			{name: "auth", label: "Login required: only users given this board can see it and open its apps", type: "checkbox",
				value: !!board.auth, wide: true}
		], function (v, changed) {
			var draft = copy(data), target;
			if (name) {
				target = boardsOf(draft).filter(function (b) { return b.name === name; })[0];
			} else {
				var id = v.name.trim();
				if (!/^[^\/\s]+\.brd$/.test(id)) { fail("The name must end in .brd and contain no spaces or '/'."); }
				if (boardsOf(draft).some(function (b) { return b.name === id; })) { fail("A board named " + id + " already exists."); }
				target = {name: id};
				draft[0].boards.push(target);
			}
			if (changed("label") || !name) { if (v.label.trim()) { target.label = v.label.trim(); } else { delete target.label; } }
			if (changed("auth") || !name) { target.auth = v.auth; }
			return saveAndShow("apps", draft, showApps);
		});
	}
	function deleteBoard(name, used) {
		confirmed("Delete the board " + name + "?" + (used ? " " + used + " app(s) list it; they are taken off it." : "") +
			" Users that list it keep it in their boards.", function () {
			var draft = copy(appsData());
			draft[0].boards = draft[0].boards.filter(function (b) { return !isObject(b) || b.name !== name; });
			allApps(draft).forEach(function (app) {
				if (asList(app.board).indexOf(name) !== -1) { app.board = asList(app.board).filter(function (b) { return b !== name; }); }
			});
			return saveAndShow("apps", draft, showApps);
		});
	}

	function boardOptions(data, selected) {
		var options = [["", "Home page (public)"]], known = {"": true};
		boardsOf(data).forEach(function (b) {
			known[b.name] = true;
			options.push([b.name, str(b.label || b.name) + (b.auth ? " (login)" : "")]);
		});
		selected.forEach(function (b) { if (!known[b]) { options.push([b, b + " (not defined)"]); } });
		return options;
	}
	function developersText(list) {
		return asList(list).filter(isObject).map(function (d) {
			return str(d.name) + (d.email ? " <" + d.email + ">" : "");
		}).join("\n");
	}
	function parseDevelopers(text) {
		return lines(text).map(function (line) {
			var match = /^(.*?)\s*<([^>]*)>$/.exec(line);
			if (match) { return {name: match[1], email: match[2].trim()}; }
			return line.indexOf("@") !== -1 && line.indexOf(" ") === -1 ? {name: "", email: line} : {name: line, email: ""};
		});
	}
	function envText(env) {
		return isObject(env) ? Object.keys(env).map(function (k) { return k + "=" + env[k]; }).join("\n") : "";
	}
	function parseEnv(text) {
		var env = {};
		lines(text).forEach(function (line) {
			var at = line.indexOf("=");
			if (at < 1) { fail("Environment: write each variable as NAME=value (" + line + ")"); }
			env[line.slice(0, at).trim()] = line.slice(at + 1);
		});
		return env;
	}
	function parseJson(text, label, kind) {
		var value;
		try { value = JSON.parse(text); } catch (e) { fail(label + ": " + e.message); }
		if (kind === "list" ? !Array.isArray(value) : !isObject(value)) { fail(label + ": expected a JSON " + (kind === "list" ? "list" : "object")); }
		return value;
	}
	function parseInteger(text, label) {
		if (!/^-?\d+$/.test(text.trim())) { fail(label + ": expected a whole number"); }
		return parseInt(text, 10);
	}
	// An empty value removes the key, so the default applies.
	function put(entry, key, value) {
		if (value === "" || value === undefined || (Array.isArray(value) && !value.length) || (isObject(value) && !Object.keys(value).length)) {
			delete entry[key];
		} else {
			entry[key] = value;
		}
	}

	// `preset`: initial values of a new app, such as {type: "docker", image: …} from the Docker tab.
	function editApp(appId, parentId, preset) {
		var data = appsData(), loc = appId ? findApp(data, appId) : null, entry = loc ? loc.entry : preset || {};
		loadImageList();
		var parent = parentId ? findApp(data, parentId).entry : null;
		var boards = loc ? asList(entry.board) : parent ? asList(parent.board) : [];
		var health = entry.health_path === undefined || entry.health_path === null ? "" : entry.health_path === "" ? "off" : "custom";
		var userHeaders = entry.streamlit_user_headers === true ? "true" : entry.streamlit_user_headers === false ? "false" : "";
		var parents = topApps(data).filter(function (a) { return a.app_id !== appId; })
			.map(function (a) { return [a.app_id, (str(a.app_name) || a.app_id) + " (" + a.app_id + ")"]; });
		var type = loc ? typeOf(entry) : entry.type || "streamlit", builtin = type === "builtin";
		function is() { var types = arguments; return function (v) { return Array.prototype.indexOf.call(types, v.type) !== -1; }; }
		var link = is("url", "curl"), local = is("streamlit", "python"), container = is("docker", "kubernetes");
		function launched(v) { return local(v) || container(v); }
		function streamlit(v) { return v.type === "streamlit" || (container(v) && v.serves === "streamlit"); }
		function currentType() { return $("f-type") ? $("f-type").value : type; }
		function currentFolder() { return $("f-folder") ? $("f-folder").value.trim() : str(entry.folder); }
		// Paths of a local app: checked on the server, relative to the config folder (folder) or to the folder (the rest).
		function localPath(relativeToFolder) {
			return function (value) {
				var kind = currentType();
				if (kind !== "streamlit" && kind !== "python") { return ["", ""]; }
				return pathCheck(value, relativeToFolder ? currentFolder() : "");
			};
		}
		openEditor(appId ? "App: " + appId : parentId ? "New app under " + parentId : "New app", [
			{type: "section", label: "General"},
			{name: "type", label: "Type", type: "select", value: type,
				options: builtin ? [["builtin", "Built-in tool"]] : APP_TYPES, describe: function (v) { return TYPE_HELP[v]; }},
			{name: "app_id", label: "App ID", value: str(entry.app_id), placeholder: "sales-report", mono: true,
				check: function (value) { return idStatus(value, appId); }, help: "Short and unique: the app's address is /<app ID>/"},
			{name: "app_name", label: "Name", value: str(entry.app_name), placeholder: "the app ID", help: "Shown on its card"},
			{name: "icon", label: "Icon", type: "image", value: str(entry.icon), placeholder: "/cdf/icons/monitor.png", wide: true,
				uploadFolder: "icons", help: "Pick a bundled icon, upload your own, or type any image URL"},
			{name: "description", label: "Description", type: "textarea", rows: 2, wide: true, value: str(entry.description)},
			{name: "display", label: "Display", type: "select", value: str(entry.display || "show"), options: META.display},
			{name: "parent", label: "Listed under", type: "select", value: parentId || "", options: [["", "Top level"]].concat(parents),
				help: "A child app shows inside its parent's card"},
			{name: "board", label: "Boards", type: "checks", wide: true, value: boards, options: boardOptions(data, boards),
				help: "Where the app is listed. Its boards also decide who can open it; admins can open every app."},
			{name: "developer", label: "Developers", type: "textarea", rows: 2, wide: true, value: developersText(entry.developer),
				placeholder: "Jane Doe <jane@example.com>", help: "One per line; Report an issue writes to them"},
			{type: "section", label: "Link", when: link},
			{name: "url", label: "URL", wide: true, value: str(entry.url), placeholder: "https://…", when: link,
				help: "Link: the app redirects to it. Proxy: the hub serves it under /<app ID>/ and keeps it hidden."},
			{type: "section", label: "Container", when: container},
			{name: "serves", label: "The image runs", type: "select", value: servesOf(entry), when: container, options: META.serves,
				help: "Streamlit apps get the hub's Streamlit flags; other servers get requests without the /<app ID> prefix"},
			{name: "image", label: "Image", value: str(entry.image), when: container, list: "docker-image-list", mono: true,
				placeholder: "registry/name:tag",
				help: "Missing images are pulled at start, within startup-timeout: pull big ones in the Docker tab first"},
			{name: "container_port", label: "Container port", type: "number", value: str(entry.container_port), when: container,
				placeholder: "8501 Streamlit, 8000 otherwise", help: "The port the app listens on inside the container"},
			{name: "volumes", label: "Volumes", type: "textarea", rows: 2, mono: true, value: asList(entry.volumes).join("\n"),
				when: is("docker"), placeholder: "/data/sales:/app/data:ro",
				help: "One per line: a path on the Docker host, or a named volume, then the path in the container, then :ro for read-only"},
			{name: "runtime_args", label: "Other docker run options", type: "textarea", rows: 2, mono: true, value: asList(entry.runtime_args).join("\n"),
				when: is("docker"), placeholder: "--memory=2g", help: "One per line, for example limits"},
			{name: "kubernetes", label: "Kubernetes options", type: "subform", form: META.subforms.kubernetes,
				value: isObject(entry.kubernetes) ? entry.kubernetes : {}, when: is("kubernetes"),
				help: "All optional. Resources, node selector and environment use Kubernetes' own JSON"},
			{type: "section", label: "Launch", when: launched},
			{name: "folder", label: "Folder", value: str(entry.folder), placeholder: "relative to the config folder", when: local,
				check: localPath(false), help: "Where the app's code is; also its working directory"},
			{name: "file", label: "Entry script", value: str(entry.file), placeholder: "main.py", when: launched,
				check: localPath(true),
				help: "Relative to the folder; in an image, a path inside it. A web server image without one runs its own command."},
			{name: "virtual_environment", label: "Python environment", value: str(entry.virtual_environment), when: local,
				placeholder: "the hub's default", list: environmentList(),
				help: "Conda env name or environment folder: start typing to see the conda envs of the server"},
			{name: "python_executable", label: "Python executable", value: str(entry.python_executable), when: local,
				check: localPath(false), help: "Overrides the environment"},
			{name: "bash_file", label: "Launcher script", value: str(entry.bash_file), when: local, check: localPath(true),
				help: "Receives the port flags and must forward them"},
			{name: "activate", label: "Run through conda run (for envs that need activation)", type: "checkbox", value: !!entry.activate, when: local},
			{name: "command", label: "Command", value: entry.command ? JSON.stringify(entry.command) : "", wide: true, mono: true, when: launched,
				placeholder: "[\"{python}\", \"main.py\", \"--port\", \"{port}\"]", help: "JSON list; replaces the entry script"},
			{name: "args", label: "Extra arguments", type: "textarea", rows: 2, value: asList(entry.args).join("\n"), when: launched,
				help: "One per line"},
			{name: "env", label: "Environment variables", type: "textarea", rows: 3, mono: true, value: envText(entry.env), when: launched,
				placeholder: "NAME=value", help: "One per line"},
			{name: "env_passthrough", label: "Hub variables passed through", type: "textarea", rows: 3, when: launched,
				value: asList(entry.env_passthrough).join("\n"), placeholder: "AWS_*", help: "One name or glob per line"},
			{type: "section", label: "Lifecycle", when: launched},
			{name: "auto_shutdown", label: "Stop on memory clean and when idle", type: "checkbox", value: entry.auto_shutdown !== false, when: launched},
			{name: "auto_start", label: "Start with the hub and after scheduled cleans", type: "checkbox", value: !!entry.auto_start, when: launched},
			{name: "idle_timeout", label: "Idle timeout (min)", type: "number", value: str(entry.idle_timeout), placeholder: "the hub's", when: launched,
				help: "0 turns it off"},
			{name: "restart", label: "Restart", type: "select", value: str(entry.restart || "never"), when: launched,
				options: META.restart, help: "Start the app again after it stops on its own"},
			{name: "health", label: "Health checks", type: "select", value: health, when: launched,
				options: [["", "Default for the app type"], ["custom", "Custom path"], ["off", "Off"]],
				help: "The hub asks the app regularly whether it still works, and stops it when it doesn't"},
			{name: "health_path", label: "Health path", value: health === "custom" ? entry.health_path : "", placeholder: "health/",
				when: function (v) { return launched(v) && v.health === "custom"; }, help: "Under /<app ID>/; answers 2xx or 3xx when healthy"},
			{name: "streamlit_user_headers", label: "Streamlit user headers", type: "select", value: userHeaders, when: streamlit,
				options: [["", "The hub's setting"], ["true", "On"], ["false", "Off"]], help: "Fill st.user"}
		], function (v, changed) { return saveApp(appId, loc && loc.parent ? loc.parent.app_id : "", v, changed, preset); });
	}

	function saveApp(originalId, oldParent, v, changed, preset) {
		var draft = copy(appsData()), id = v.app_id.trim(), container = v.type === "docker" || v.type === "kubernetes";
		if (id !== originalId) {
			var status = idStatus(id, originalId);
			if (status[0] !== "ok") { fail(status[1] || "Type an app ID."); }
		}
		if (container && !v.image.trim()) { fail("Type the image to run."); }
		if ((v.type === "url" || v.type === "curl") && !v.url.trim()) { fail("Type the URL."); }
		var loc = originalId ? findApp(draft, originalId) : null;
		var entry = loc ? loc.entry : Object.assign({board: v.board, app_id: id}, preset ? copy(preset) : {});
		entry.app_id = id;
		if (v.type !== "builtin" && (!loc || changed("type") || changed("serves"))) {
			entry.type = v.type;
			delete entry.runtime;  // `type` says where the app runs
			if (container) { entry.serves = v.serves; } else { delete entry.serves; }
		}
		if (changed("board")) { entry.board = v.board; }
		["app_name", "description", "icon", "url", "file", "folder", "virtual_environment", "python_executable", "bash_file", "image"]
			.forEach(function (key) { if (changed(key)) { put(entry, key, v[key].trim()); } });
		["display", "restart"].forEach(function (key) { if (changed(key)) { entry[key] = v[key]; } });
		["activate", "auto_shutdown", "auto_start"].forEach(function (key) { if (changed(key)) { entry[key] = v[key]; } });
		["args", "env_passthrough", "runtime_args", "volumes"].forEach(function (key) { if (changed(key)) { put(entry, key, lines(v[key])); } });
		["idle_timeout", "container_port"].forEach(function (key) {
			if (changed(key)) { put(entry, key, v[key].trim() === "" ? "" : parseInteger(v[key], key)); }
		});
		if (changed("volumes") && lines(v.volumes).some(function (x) { return x.charAt(0) === "-" || x.indexOf(":") === -1; })) {
			fail("Write each volume as source:/path/in/container, with :ro at the end for read-only.");
		}
		if (changed("developer")) { entry.developer = parseDevelopers(v.developer); }
		if (changed("command")) { put(entry, "command", v.command.trim() ? parseJson(v.command, "Command", "list") : ""); }
		if (changed("env")) { put(entry, "env", parseEnv(v.env)); }
		if (changed("kubernetes")) { put(entry, "kubernetes", v.kubernetes); }
		if (changed("streamlit_user_headers")) { put(entry, "streamlit_user_headers", v.streamlit_user_headers === "" ? "" : v.streamlit_user_headers === "true"); }
		if (changed("health") || changed("health_path")) {
			if (v.health === "custom" && !v.health_path.trim()) { fail("Type the health path, or pick another health check option."); }
			if (v.health === "") { delete entry.health_path; } else { entry.health_path = v.health === "off" ? "" : v.health_path.trim(); }
		}
		if (!loc || v.parent !== oldParent) {
			if (loc) { loc.list.splice(loc.index, 1); }
			if (v.parent) {
				if (asList(entry.children).length) { fail("This app has child apps, so it can't be listed under another app."); }
				delete entry.children;
				var parent = findApp(draft, v.parent).entry;
				parent.children = Array.isArray(parent.children) ? parent.children : [];
				parent.children.push(entry);
			} else if (loc && !loc.parent) {
				draft.splice(loc.index, 0, entry);
			} else {
				draft.push(entry);
			}
		}
		return saveAndShow("apps", draft, showApps);
	}
	function deleteApp(appId) {
		var loc = findApp(appsData(), appId), children = asList(loc.entry.children).filter(isApp).length;
		confirmed("Delete the app " + appId + "?" + (children ? " Its " + children + " child app(s) are deleted too." : ""), function () {
			var draft = copy(appsData()), target = findApp(draft, appId);
			target.list.splice(target.index, 1);
			return saveAndShow("apps", draft, showApps);
		});
	}
	$("board-add").addEventListener("click", function () { editBoard(null); });
	$("app-add").addEventListener("click", function () { editApp(null, ""); });

	// -- users --
	function isUser(entry) { return isObject(entry) && (str(entry.source || "local") !== "local" || "password" in entry); }
	function currentUser() {
		var name = document.querySelector("#sh-user-btn .sh-user-name");
		return name ? name.firstChild.textContent.trim() : "";
	}
	function showUsers() {
		return Promise.all([load("users"), load("apps")]).then(renderUsers).catch(function (error) { showError($("users"), error.message); });
	}
	function renderUsers() {
		var file = files.users, box = $("users"), note = $("users-note");
		var data = file.data === null && !file.error ? {} : file.data;
		$("user-add").disabled = !!file.error || !isObject(data);
		note.textContent = (file.exists ? "" : "There is no users file yet at " + file.path + ": adding a user creates it. ") +
			"Passwords are never shown; a new one is hashed when you save. The STREAMHUB_ADMIN_PASSWORD admin is not in this file.";
		if (file.error || !isObject(data)) { showError(box, file.error || "The users file must be a JSON object. Fix it in JSON files."); return; }
		clear(box);
		var users = table(["User", "Sign-in", "Role", "Boards", ""]), names = Object.keys(data).filter(function (n) { return isUser(data[n]); });
		names.forEach(function (name) {
			var user = data[name], row = el("tr"), who = el("div", null, "sh-app-cell");
			who.appendChild(el("b", name));
			if (name === currentUser()) { who.appendChild(el("small", "you")); }
			cell(row, "User", who);
			cell(row, "Sign-in", el("span", str(user.source || "local") === "local" ? "password" : user.source, "sh-chip sh-chip-muted"));
			cell(row, "Role", str(user.role || "user"));
			cell(row, "Boards", chips(asList(user.boards).map(function (b) { return b === "*" ? "all" : b === "" ? "Home page" : b; }), "none"));
			cell(row, "", actions([
				["fa-pencil", "Edit", "", function () { editUser(name); }],
				["fa-trash", "Delete", "is-bad", function () { deleteUser(name); }]
			]), "text-right");
			users.body.appendChild(row);
		});
		box.appendChild(names.length ? users.node : el("p", "No users in the file.", "sh-muted"));
	}
	function editUser(name) {
		var data = files.users.data || {}, user = name ? data[name] : {}, boards = asList(user.boards);
		var apps = appsData(), options = [["*", "All boards"]], known = {"*": true};
		(apps ? boardsOf(apps) : []).forEach(function (b) {
			known[b.name] = true;
			options.push([b.name, str(b.label || b.name) + (b.auth ? "" : " (public)")]);
		});
		boards.forEach(function (b) { if (!known[b]) { options.push([b, b === "" ? "Home page" : b + " (not defined)"]); } });
		function local(v) { return v.source === "local"; }
		openEditor(name ? "User: " + name : "New user", [
			{name: "name", label: "User name", value: name || "", readonly: !!name, help: name ? "Fixed: delete and add the user to rename it" : ""},
			{name: "source", label: "Sign-in", type: "select", value: str(user.source || "local"),
				options: [["local", "Password"], ["oidc", "Single sign-on (OpenID Connect)"], ["ldap", "LDAP"]],
				help: "A single sign-on entry sets that account's role and boards instead of the group mapping"},
			{name: "password", label: "Password", type: "password", value: "", when: local, generate: true,
				placeholder: name && "password" in user ? "unchanged" : "",
				help: (name && "password" in user ? "Leave empty to keep the current password. " : "") +
					"Generate shows a new password once: copy it for the user. It is stored as a hash."},
			{name: "role", label: "Role", type: "select", value: str(user.role || "user"), options: choiceOptions("roles")},
			{name: "boards", label: "Boards", type: "checks", wide: true, value: boards, options: options,
				help: "The login boards this user can see. Admins see every board."}
		], function (v, changed) {
			var draft = copy(data), id = v.name.trim(), entry;
			if (name) {
				entry = draft[name];
			} else {
				if (!id) { fail("Type a user name."); }
				if (id in draft) { fail("There is already a user named " + id + "."); }
				entry = draft[id] = {};
			}
			if (changed("source") || !name) { if (v.source === "local") { delete entry.source; } else { entry.source = v.source; } }
			if (v.source === "local") {
				if (v.password) { entry.password = v.password; } else if (!("password" in entry)) { fail("Type a password."); }
			} else {
				delete entry.password;
			}
			if (changed("role") || !name) { entry.role = v.role; }
			if (changed("boards") || !name) { entry.boards = v.boards; }
			return saveAndShow("users", draft, showUsers);
		});
	}
	function deleteUser(name) {
		var self = name === currentUser();
		confirmed("Delete the user " + name + "?" + (self ? " This is you: you will be logged out." : ""), function () {
			var draft = copy(files.users.data);
			delete draft[name];
			return saveAndShow("users", draft, showUsers);
		});
	}
	$("user-add").addEventListener("click", function () { editUser(null); });

	// -- news --
	var NEWS_TYPES = META.newsTypes;
	function showNews() {
		return load("news").then(renderNews).catch(function (error) { showError($("news"), error.message); });
	}
	function newsData() {
		var data = files.news.data === null && !files.news.error ? [] : files.news.data;
		return Array.isArray(data) ? data : null;
	}
	function renderNews() {
		var box = $("news"), data = newsData();
		$("news-add").disabled = !data;
		if (!data) { showError(box, files.news.error || "The news file must be a JSON list. Fix it in JSON files."); return; }
		clear(box);
		var news = table(["Title", "Date", "Type", "Message", ""]), count = 0;
		data.forEach(function (item, index) {
			if (!isObject(item)) { return; }
			count++;
			var row = el("tr");
			cell(row, "Title", el("b", str(item.title) || "(no title: not shown)"));
			cell(row, "Date", str(item.date) || "–", "nowrap");
			cell(row, "Type", el("span", str(item.type || "normal"), "sh-chip sh-chip-muted"));
			cell(row, "Message", el("span", str(item.message), "sh-clamp"));
			cell(row, "", actions([
				["fa-arrow-up", "Move up", "", function () { moveNews(index, -1); }],
				["fa-arrow-down", "Move down", "", function () { moveNews(index, 1); }],
				["fa-pencil", "Edit", "", function () { editNews(index); }],
				["fa-trash", "Delete", "is-bad", function () { deleteNews(index); }]
			]), "text-right");
			news.body.appendChild(row);
		});
		box.appendChild(count ? news.node : el("p", "No news yet.", "sh-muted"));
	}
	function editNews(index) {
		var data = newsData(), item = index === null ? {} : data[index];
		openEditor(index === null ? "New announcement" : "Announcement", [
			{name: "title", label: "Title", value: str(item.title), wide: true},
			{name: "date", label: "Date", value: str(item.date), placeholder: new Date().toISOString().slice(0, 10), help: "Shown as written"},
			{name: "type", label: "Type", type: "select", value: str(item.type || "normal"), options: NEWS_TYPES},
			{name: "message", label: "Message", type: "textarea", rows: 4, wide: true, value: str(item.message)}
		], function (v, changed) {
			if (!v.title.trim()) { fail("Type a title."); }
			var draft = copy(data), entry = index === null ? {} : draft[index];
			["title", "date", "type", "message"].forEach(function (key) {
				if (changed(key) || index === null) { entry[key] = v[key].trim(); }
			});
			if (index === null) { draft.unshift(entry); }  // newest first: the home page shows the first three
			return saveAndShow("news", draft, showNews);
		});
	}
	function moveNews(index, step) {
		var draft = copy(newsData()), target = index + step;
		while (target >= 0 && target < draft.length && !isObject(draft[target])) { target += step; }
		if (target < 0 || target >= draft.length) { return; }
		var item = draft.splice(index, 1)[0];
		draft.splice(target, 0, item);
		saveAndShow("news", draft, showNews).catch(function (error) { A.toast(error.message, true); });
	}
	function deleteNews(index) {
		confirmed("Delete the announcement \"" + str(newsData()[index].title) + "\"?", function () {
			var draft = copy(newsData());
			draft.splice(index, 1);
			return saveAndShow("news", draft, showNews);
		});
	}
	$("news-add").addEventListener("click", function () { editNews(null); });

	// -- settings (streamhub.json) --
	var FORM = JSON.parse($("settings-form").textContent), settingsFields = [], settingsDirty = false;
	function showSettings() {
		if (settingsDirty) { return Promise.resolve(); }  // keep unsaved edits when coming back to the tab
		// The apps file gives the boards that group mapping rules can grant; the settings show without it.
		return Promise.all([load("config"), load("apps").catch(function () {})]).then(function () { renderSettings(); })
			.catch(function (error) { showError($("settings"), error.message); });
	}
	function boardChoices() {
		var data = files.apps && appsData();
		return [["*", "All boards"]].concat(data ? boardsOf(data).map(function (b) { return [b.name, str(b.label || b.name)]; }) : []);
	}
	function settingSpec(field, data) {
		var value = data[field.key], kind = field.kind.split(":")[0], list = field.kind.split(":")[1];
		var spec = {name: "s-" + field.key, key: field.key, label: field.label, placeholder: field.placeholder, help: field.help,
			badge: [field.restart ? "restart" : "", field.envSet ? "set by " + field.env : ""].filter(Boolean)};
		if (field.envSet) {  // the environment wins over the file: editing the file would change nothing
			spec.readonly = true;
			spec.help = "Set by the environment variable " + field.env + ", which wins over this file. " + field.help;
		}
		if (kind === "bool") {
			spec.type = "checkbox";
			spec.value = value === true;
			spec.label = field.label + (field.restart ? " (restart)" : "");
		} else if (kind === "choice") {
			spec.type = "select";
			spec.value = str(value);
			spec.options = [["", "Default (" + field.placeholder + ")"]].concat(CHOICES[list] ? choiceOptions(list) :
				list.split(",").map(function (o) { return [o, o]; }));
			if (spec.value && !spec.options.some(function (o) { return o[0] === spec.value; })) { spec.options.push([spec.value, spec.value]); }
		} else if (kind === "layout") {
			spec.type = "select";
			spec.value = str(value);
			spec.options = [["", "Default (" + field.placeholder + ")"]].concat(META.layouts.map(function (l) { return [l[0], l[1] + " (" + l[0] + ")"]; }));
			if (spec.value && !META.layouts.some(function (l) { return l[0] === spec.value; })) {
				var renamed = META.renamedLayouts[spec.value];  // still works; choosing the new name updates the file
				spec.options.push([spec.value, spec.value + (renamed ? " (old name of " + renamed + ")" : " (not found)")]);
			}
		} else if ((kind === "object" || kind === "list") && list) {
			spec.type = kind === "object" ? "subform" : "rows";
			spec.form = META.subforms[list];
			spec.value = value;
			spec.boards = boardChoices();
			spec.addLabel = "Add " + (list === "notifiers" ? "a channel" : "a rule");
		} else if (kind === "object" || kind === "list") {
			spec.type = "textarea";
			spec.rows = 4;
			spec.mono = true;
			spec.wide = true;
			spec.value = value === undefined || value === null || value === "" ? "" : JSON.stringify(value, null, 2);
		} else if (kind === "ints" || kind === "strings") {
			spec.value = Array.isArray(value) ? value.join(", ") : str(value);
		} else if (kind === "schedule") {
			spec.type = "schedule";
			// null or "off" turns the daily clean off, while a missing key means the default.
			spec.value = (value === null && "schedule" in data) || value === "off" ? "off" : str(value);
		} else {
			spec.type = {int: "number", secret: "password", image: "image"}[kind] || "text";
			spec.value = str(value);
			if (kind === "image") { spec.wide = true; }
			if (kind === "timezone") { spec.list = "timezone-list"; }
			if (kind === "environment") { spec.list = environmentList(); }
			if (kind === "path") { spec.check = function (v) { return pathCheck(v, ""); }; }
		}
		return spec;
	}
	function settingValue(field, raw) {
		var kind = field.kind.split(":")[0];
		if (kind === "bool") { return raw; }
		if (kind === "object" || kind === "list") {
			if (typeof raw !== "string") { return (Array.isArray(raw) ? raw.length : Object.keys(raw).length) ? raw : undefined; }
		}
		raw = raw.trim();
		if (raw === "") { return undefined; }
		if (kind === "int") { return parseInteger(raw, field.label); }
		if (kind === "ints") {
			var parts = raw.split(/[\s,]+/).filter(Boolean);
			if (!parts.every(function (p) { return /^\d+$/.test(p); })) { fail(field.label + ": expected port numbers separated by commas"); }
			return parts.map(Number);
		}
		if (kind === "strings") { return raw.split(/[\s,]+/).filter(Boolean); }
		if (kind === "object" || kind === "list") { return parseJson(raw, field.label, kind); }
		return raw;
	}
	function renderSettings() {
		var box = $("settings"), file = files.config, data = file.data === null && !file.error ? {} : file.data;
		clear(box);
		settingsFields = [];
		settingsDirty = false;
		var result = el("div", null, "sh-alert");
		result.id = "settings-result";
		result.hidden = true;
		box.appendChild(result);
		$("settings-save").disabled = !!file.error || !isObject(data);
		if (file.error || !isObject(data)) { showError(box, file.error || "The config file must be a JSON object. Fix it in JSON files."); return; }
		FORM.forEach(function (section) {
			var card = el("div", null, "sh-card"), head = el("div", null, "sh-card-head"), grid = el("div", null, "sh-form-grid");
			head.appendChild(el("h2", section.title));
			card.appendChild(head);
			if (section.help) { card.appendChild(el("p", section.help, "sh-muted small sh-section-help")); }
			section.fields.forEach(function (field) {
				var built = buildField(settingSpec(field, data));
				built.field = field;
				grid.appendChild(built.node);
				settingsFields.push(built);
			});
			card.appendChild(grid);
			box.appendChild(card);
		});
	}
	function settingsResult(message, bad, restart) {
		var box = $("settings-result");
		clear(box);
		box.className = "sh-alert " + (bad ? "sh-alert-bad" : "sh-alert-ok");
		box.appendChild(el("span", message));
		if (restart && restart.length) {
			var link = el("a", null, "btn btn-sm sh-btn-quiet sh-alert-action");
			link.href = "/restart/";
			link.appendChild(el("i", null, "fa fa-repeat"));
			link.appendChild(document.createTextNode(" Restart now"));
			box.appendChild(link);
		}
		box.hidden = false;
		box.scrollIntoView({block: "nearest"});
	}
	$("settings").addEventListener("input", function () { settingsDirty = true; });
	$("settings").addEventListener("change", function () { settingsDirty = true; });
	$("settings-reset").addEventListener("click", function () { settingsDirty = false; showSettings(); });
	$("settings-save").addEventListener("click", function () {
		var draft = copy(files.config.data || {}), count = 0;
		try {
			settingsFields.forEach(function (built) {
				if (!built.changed()) { return; }
				count++;
				if (built.validate) { built.validate(); }
				var value = settingValue(built.field, built.get());
				if (value === undefined) { delete draft[built.field.key]; } else { draft[built.field.key] = value; }
			});
		} catch (error) { settingsResult(error.message, true); return; }
		if (!count) { settingsResult("Nothing changed.", false); return; }
		var button = this;
		button.disabled = true;
		save("config", draft)
			.then(function (r) {
				return load("config").then(function () { renderSettings(); settingsResult(r.message, false, r.restart); });
			})
			.catch(function (error) { settingsResult(error.message, true); })
			.then(function () { button.disabled = false; });
	});

	// -- Docker: the daemon, containers and images --
	var docker = null, containerFilter = "all";
	var DOCKER_STATES = {running: "running", restarting: "starting", paused: "starting", exited: "stopped", dead: "unhealthy"};
	var imageList = el("datalist");
	imageList.id = "docker-image-list";  // offered by the Image field of the app editor
	document.body.appendChild(imageList);
	function fillImageList() {
		clear(imageList);
		(docker ? docker.images : []).forEach(function (image) {
			if (image.repository === "<none>") { return; }
			var option = el("option");
			option.value = image.reference;
			imageList.appendChild(option);
		});
	}
	function loadImageList() {
		if (!docker) { A.api("GET", "/api/admin/docker").then(function (state) { docker = state; fillImageList(); }).catch(function () {}); }
	}
	function showDocker() {
		return A.api("GET", "/api/admin/docker").then(function (state) {
			docker = state;
			fillImageList();
			renderDocker();
		}).catch(function (error) { showError($("docker-state"), error.message); });
	}
	function facts(rows) {
		var box = el("dl", null, "sh-facts");
		rows.forEach(function (row) {
			box.appendChild(el("dt", row[0]));
			var value = el("dd");
			if (row[1] instanceof Node) { value.appendChild(row[1]); } else { value.textContent = row[1]; }
			box.appendChild(value);
		});
		return box;
	}
	function renderDocker() {
		var state = docker, box = $("docker-state");
		clear(box);
		var server = state.server ? "Docker " + state.server.Version + " (" + state.server.Os + "/" + state.server.Arch + ")" : "not reachable";
		var network = el("span", state.network || "none: containers are published on 127.0.0.1");
		if (state.network && state.network_exists === false) { network.appendChild(el("b", " · missing", "text-danger")); }
		box.appendChild(facts([
			["Client", state.cli || "not installed"],
			["Daemon", state.host ? state.host : state.default_host + " (default)"],
			["Server", server],
			["App network", network]
		]));
		if (state.error) { box.appendChild(el("div", state.error, "sh-alert sh-alert-bad small")); }
		if (state.network && state.network_exists === false) {
			box.appendChild(el("div", "The network " + state.network + " does not exist. Create it with `docker network create " +
				state.network + "` and connect the hub's container to it.", "sh-alert sh-alert-bad small"));
		}
		var hint = el("p", null, "sh-muted small mb-0");
		hint.appendChild(document.createTextNode("Change the socket and the network in "));
		var link = el("a", "Settings → Docker");
		link.href = "#settings";
		hint.appendChild(link);
		hint.appendChild(document.createTextNode(". Docker apps have the type Docker image (Apps tab, or New app on an image below)."));
		box.appendChild(hint);
		$("docker-pull").querySelector("button").disabled = !state.server;
		renderContainers();
		renderImages();
	}
	function dockerAction(url, body, label) {
		A.toast(label + "…");
		return A.api("POST", url, body).then(function (r) {
			A.toast(r.ok ? label + ": done" : label + ": " + (r.output || "failed"), !r.ok);
			return showDocker().then(function () { return r; });
		});
	}
	function showText(title, text) {
		$("text-title").textContent = title;
		$("text-body").textContent = text || "No output.";
		A.openModal("text-box");
		$("text-body").scrollTop = $("text-body").scrollHeight;
	}
	$("text-close").addEventListener("click", function () { A.closeModal("text-box"); });
	function renderContainers() {
		var box = $("docker-containers");
		clear(box);
		var query = $("containers-search").value.trim().toLowerCase();
		var rows = docker.containers.filter(function (c) {
			return (containerFilter === "all" || (containerFilter === "apps" ? c.app : c.state === "running")) &&
				(c.name + " " + c.image + " " + c.app).toLowerCase().indexOf(query) !== -1;
		}).sort(function (a, b) { return ((b.state === "running") - (a.state === "running")) || a.name.localeCompare(b.name); });
		if (!rows.length) { box.appendChild(el("p", docker.server ? "No containers match." : "", "sh-muted")); return; }
		var list = table(["Container", "Image", "State", "Ports", "App", ""]);
		rows.forEach(function (c) {
			var row = el("tr"), name = el("div", null, "sh-app-cell"), pill = el("span", null, "sh-pill is-" + (DOCKER_STATES[c.state] || "not-running"));
			var url = "/api/admin/docker/containers/" + encodeURIComponent(c.name) + "/";
			name.appendChild(el("b", c.name));
			name.appendChild(el("small", c.id + (c.hub ? " · this hub" : "")));
			cell(row, "Container", name);
			cell(row, "Image", c.image, "sh-mono sh-cut").title = c.image;
			pill.appendChild(el("i", null, "hub-badge state-" + (DOCKER_STATES[c.state] || "not-running")));
			pill.appendChild(document.createTextNode(c.state));
			var status = el("div");
			status.appendChild(pill);
			status.appendChild(el("small", c.status, "sh-muted d-block"));
			cell(row, "State", status);
			cell(row, "Ports", c.ports || "–", "sh-mono small");
			cell(row, "App", c.app || "–", "sh-mono");
			var running = c.state === "running", buttons = [];
			var warn = c.hub ? " This is the hub's own container: Streamhub stops with it." :
				c.app ? " It runs the app " + c.app + ": the hub sees it stop, and its restart policy applies." : "";
			if (running) {
				buttons.push(["fa-stop", "Stop", "is-bad", function () {
					if (window.confirm("Stop the container " + c.name + "?" + warn)) { dockerAction(url + "stop", undefined, "Stop " + c.name); }
				}]);
				buttons.push(["fa-repeat", "Restart", "is-warn", function () { dockerAction(url + "restart", undefined, "Restart " + c.name); }]);
			} else {
				buttons.push(["fa-play", "Start", "is-ok", function () { dockerAction(url + "start", undefined, "Start " + c.name); }]);
			}
			buttons.push(["fa-terminal", "Logs", "", function () {
				A.api("GET", url + "logs").then(function (text) { showText("Logs: " + c.name, text); })
					.catch(function (error) { A.toast(error.message, true); });
			}]);
			buttons.push(["fa-trash", "Remove", "is-bad", function () {
				if (window.confirm("Remove the container " + c.name + (running ? ", which is running" : "") + "?" + warn)) {
					dockerAction(url + "remove", undefined, "Remove " + c.name);
				}
			}]);
			cell(row, "", actions(buttons), "text-right");
			list.body.appendChild(row);
		});
		box.appendChild(list.node);
	}
	Array.prototype.forEach.call(document.querySelectorAll("[data-containers]"), function (button) {
		button.addEventListener("click", function () {
			containerFilter = button.getAttribute("data-containers");
			Array.prototype.forEach.call(document.querySelectorAll("[data-containers]"), function (b) { b.classList.toggle("active", b === button); });
			if (docker) { renderContainers(); }
		});
	});
	function renderImages() {
		var box = $("docker-images");
		clear(box);
		var query = $("images-search").value.trim().toLowerCase();
		var images = docker.images.filter(function (image) { return (image.reference + " " + image.id).toLowerCase().indexOf(query) !== -1; });
		if (!images.length) { box.appendChild(el("p", docker.server ? "No images match." : "", "sh-muted")); return; }
		var list = table(["Image", "ID", "Size", "Created", "Containers", ""]);
		images.forEach(function (image) {
			var row = el("tr"), named = image.repository !== "<none>";
			cell(row, "Image", el("b", named ? image.reference : "<none>"), "sh-mono sh-cut").title = image.reference;
			cell(row, "ID", image.id, "sh-mono small");
			cell(row, "Size", image.size, "nowrap");
			cell(row, "Created", image.created, "nowrap");
			cell(row, "Containers", image.containers === "N/A" ? "–" : String(image.containers));
			var buttons = [];
			if (named) {
				buttons.push(["fa-plus", "New app from this image", "is-ok", function () { newAppFromImage(image.reference); }]);
				buttons.push(["fa-download", "Pull again", "", function () { pull(image.reference); }]);
			}
			buttons.push(["fa-trash", "Remove", "is-bad", function () {
				if (window.confirm("Remove the image " + image.reference + "?")) {
					dockerAction("/api/admin/docker/images/remove", {image: named ? image.reference : image.id}, "Remove " + image.reference);
				}
			}]);
			cell(row, "", actions(buttons), "text-right");
			list.body.appendChild(row);
		});
		box.appendChild(list.node);
	}
	function newAppFromImage(reference) {
		location.hash = "#apps";
		load("apps").then(function () {
			if (!appsData()) { A.toast("The apps file can't be edited: fix it in JSON files.", true); return; }
			editApp(null, "", {type: "docker", image: reference});
		}).catch(function (error) { A.toast(error.message, true); });
	}
	function pull(reference) {
		var result = $("docker-result"), button = $("docker-pull").querySelector("button");
		result.textContent = "Pulling " + reference + "… large images take minutes.";
		result.className = "small sh-muted";
		button.disabled = true;
		return A.api("POST", "/api/admin/docker/images/pull", {image: reference}).then(function (r) {
			result.textContent = r.ok ? "Pulled " + reference + "." : "Pull failed: " + r.output;
			result.className = "small " + (r.ok ? "text-success" : "text-danger");
			return showDocker();
		}).catch(function (error) {
			result.textContent = error.message;
			result.className = "small text-danger";
		}).then(function () { button.disabled = false; });
	}
	$("docker-pull").addEventListener("submit", function (event) {
		event.preventDefault();
		var reference = $("docker-pull-image").value.trim();
		if (reference) { pull(reference); }
	});
	$("docker-load").addEventListener("click", showDocker);
	$("containers-search").addEventListener("input", function () { if (docker) { renderContainers(); } });
	$("images-search").addEventListener("input", function () { if (docker) { renderImages(); } });

	// -- static files: the cdf folder, served at /cdf/ --
	var cdf = null, cdfFolder = "", XSRF = document.querySelector("meta[name=xsrf]").content;
	var MAX_UPLOAD = 16 * 1024 * 1024 - 64 * 1024;  // the hub's request limit, less the form overhead
	function parentOf(path) { var at = path.lastIndexOf("/"); return at === -1 ? "" : path.slice(0, at); }
	function nameOf(path) { return path.slice(path.lastIndexOf("/") + 1); }
	function join(folder, name) { return folder ? folder + "/" + name : name; }
	function cdfUrl(path) { return "/cdf/" + path.split("/").map(encodeURIComponent).join("/"); }
	function size(bytes) {
		var units = ["B", "KB", "MB", "GB"], i = 0;
		while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
		return bytes.toFixed(i ? 1 : 0) + " " + units[i];
	}
	function showStatic() {
		return A.api("GET", "/api/admin/cdf").then(function (data) {
			cdf = data;
			if (cdfFolder && !cdf.entries.some(function (e) { return e.dir && e.path === cdfFolder; })) { cdfFolder = ""; }
			renderStatic();
		}).catch(function (error) { showError($("cdf"), error.message); });
	}
	function openFolder(path) {
		cdfFolder = path;
		$("cdf-search").value = "";
		renderStatic();
	}
	function renderStatic() {
		var crumbs = $("cdf-crumbs"), note = $("cdf-note"), box = $("cdf");
		clear(crumbs);
		var parts = cdfFolder ? cdfFolder.split("/") : [], root = el("a", "cdf");
		root.href = "#static";
		root.addEventListener("click", function (event) { event.preventDefault(); openFolder(""); });
		crumbs.appendChild(root);
		parts.forEach(function (part, i) {
			crumbs.appendChild(document.createTextNode(" / "));
			var link = el("a", part);
			link.href = "#static";
			link.addEventListener("click", function (event) { event.preventDefault(); openFolder(parts.slice(0, i + 1).join("/")); });
			crumbs.appendChild(link);
		});
		note.textContent = "Served at /cdf/ from " + cdf.root + "." +
			(cdf.bundled ? " This is the folder bundled with Streamhub: an upgrade or a new container replaces it, so set cdf in Settings to a folder of your config to keep your files." : "") +
			(!cdf.exists ? " The folder does not exist yet: an upload creates it." : !cdf.writable ? " The hub can't write to this folder." : "");
		clear(box);
		var query = $("cdf-search").value.trim().toLowerCase();
		var rows = cdf.entries.filter(function (e) { return query ? e.path.toLowerCase().indexOf(query) !== -1 : parentOf(e.path) === cdfFolder; });
		rows.sort(function (a, b) { return (b.dir - a.dir) || a.path.localeCompare(b.path); });
		var list = table(["Name", "Size", "Modified", ""]);
		if (cdfFolder && !query) {
			var up = el("tr"), back = el("a", null, "sh-file");
			back.href = "#static";
			back.appendChild(el("i", null, "fa fa-level-up"));
			back.appendChild(el("span", ".."));
			back.addEventListener("click", function (event) { event.preventDefault(); openFolder(parentOf(cdfFolder)); });
			cell(up, "Name", back);
			cell(up, "Size", "");
			cell(up, "Modified", "");
			cell(up, "", "");
			list.body.appendChild(up);
		}
		rows.forEach(function (entry) {
			var row = el("tr"), link = el("a", null, "sh-file"), label = query ? entry.path : nameOf(entry.path);
			if (entry.dir) {
				link.href = "#static";
				link.appendChild(el("i", null, "fa fa-folder"));
				link.addEventListener("click", function (event) { event.preventDefault(); openFolder(entry.path); });
			} else {
				link.href = cdfUrl(entry.path);
				link.target = "_blank";
				link.rel = "noopener";
				if (IMAGE_FILE.test(entry.path)) {
					var thumb = el("img", null, "sh-thumb");
					thumb.src = cdfUrl(entry.path);
					thumb.alt = "";
					thumb.loading = "lazy";
					link.appendChild(thumb);
				} else {
					link.appendChild(el("i", null, "fa fa-file-o"));
				}
			}
			link.appendChild(el("span", label));
			cell(row, "Name", link);
			cell(row, "Size", entry.dir ? "–" : size(entry.size), "nowrap");
			cell(row, "Modified", entry.modified.replace("T", " "), "nowrap sh-muted");
			var buttons = [];
			if (!entry.dir) {
				buttons.push(["fa-link", "Copy URL", "", function () {
					var url = cdfUrl(entry.path);
					(navigator.clipboard ? navigator.clipboard.writeText(url) : Promise.reject())
						.then(function () { A.toast("Copied " + url); }, function () { window.prompt("URL of the file:", url); });
				}]);
			}
			buttons.push(["fa-pencil", "Rename or move", "", function () { renameStatic(entry); }]);
			buttons.push(["fa-trash", "Delete", "is-bad", function () {
				confirmed("Delete " + entry.path + (entry.dir ? " (an empty folder)" : "") + "? Pages that use it break.", function () {
					return cdfPost("delete", {path: entry.path}).then(showStatic);
				});
			}]);
			cell(row, "", actions(buttons), "text-right");
			list.body.appendChild(row);
		});
		box.appendChild(rows.length || cdfFolder ? list.node : el("p", query ? "No file matches." : "No files yet.", "sh-muted"));
		if (cdf.truncated) { box.appendChild(el("p", "Only the first 5000 entries are listed.", "sh-muted small")); }
	}
	function cdfPost(action, body) {
		return A.api("POST", "/api/admin/cdf/" + action, body).then(function (r) {
			if (!r.ok) { fail(r.error); }
			A.toast(r.message.charAt(0).toUpperCase() + r.message.slice(1));
			return r;
		});
	}
	function renameStatic(entry) {
		openEditor((entry.dir ? "Folder: " : "File: ") + entry.path, [
			{name: "to", label: "New path", value: entry.path, wide: true, mono: true,
				help: "Relative to the cdf folder. Change the folder part to move it; missing folders are created. Pages that use the old URL break."}
		], function (v) {
			var to = v.to.trim().replace(/^\/+/, "");
			if (!to || to === entry.path) { fail("Type a new path."); }
			return cdfPost("rename", {from: entry.path, to: to}).then(showStatic);
		});
	}
	$("cdf-folder").addEventListener("click", function () {
		openEditor("New folder in " + (cdfFolder || "cdf"), [
			{name: "name", label: "Folder name", value: "", wide: true}
		], function (v) {
			if (!v.name.trim()) { fail("Type a name."); }
			return cdfPost("folder", {path: join(cdfFolder, v.name.trim())}).then(showStatic);
		});
	});
	function upload(files, overwrite) {
		var total = files.reduce(function (sum, f) { return sum + f.size; }, 0);
		if (total > MAX_UPLOAD) { A.toast("Too big: an upload holds at most 16 MB (" + size(total) + " chosen).", true); return; }
		var form = new FormData();
		files.forEach(function (f) { form.append("files", f, f.name); });
		A.toast("Uploading " + files.length + " file(s)…");
		fetch("/api/admin/cdf/upload?folder=" + encodeURIComponent(cdfFolder) + (overwrite ? "&overwrite=1" : ""), {
			method: "POST", body: form, credentials: "same-origin", headers: {"X-XSRFToken": XSRF}
		}).then(function (response) {
			return response.json().catch(function () { return {ok: false, error: response.status + " " + response.statusText}; })
				.then(function (r) { return {status: response.status, body: r}; });
		}).then(function (r) {
			if (r.status === 409 && !overwrite) {
				if (window.confirm(r.body.error + ". Replace?")) { upload(files, true); }
				return;
			}
			if (!r.body.ok) { A.toast(r.body.error, true); return; }
			A.toast("Uploaded " + files.length + " file(s)");
			showStatic();
		}).catch(function () { A.toast("The upload failed.", true); });
	}
	$("cdf-files").addEventListener("change", function () {
		var files = Array.prototype.slice.call(this.files);
		this.value = "";
		if (files.length) { upload(files, false); }
	});
	$("cdf-search").addEventListener("input", function () { if (cdf) { renderStatic(); } });
	var card = $("cdf-card");
	["dragenter", "dragover"].forEach(function (name) {
		card.addEventListener(name, function (event) {
			if (event.dataTransfer && Array.prototype.indexOf.call(event.dataTransfer.types, "Files") !== -1) {
				event.preventDefault();
				card.classList.add("is-drop");
			}
		});
	});
	["dragleave", "drop"].forEach(function (name) {
		card.addEventListener(name, function (event) {
			if (name === "dragleave" && card.contains(event.relatedTarget)) { return; }
			card.classList.remove("is-drop");
		});
	});
	card.addEventListener("drop", function (event) {
		event.preventDefault();
		var files = Array.prototype.slice.call(event.dataTransfer.files);
		if (files.length) { upload(files, false); }
	});

	// -- backup and restore --
	var FILE_LABELS = {config: "Settings (streamhub.json)", apps: "Apps and boards", users: "Users", news: "News"};
	function restoreResult(box, message, bad, restart) {
		var alert = el("div", null, "sh-alert " + (bad ? "sh-alert-bad" : "sh-alert-ok"));
		alert.appendChild(el("span", message));
		if (restart && restart.length) {
			var link = el("a", null, "btn btn-sm sh-btn-quiet sh-alert-action");
			link.href = "/restart/";
			link.appendChild(el("i", null, "fa fa-repeat"));
			link.appendChild(document.createTextNode(" Restart now"));
			alert.appendChild(link);
		}
		box.appendChild(alert);
	}
	function showRestore(backup, fileName) {
		var box = $("restore-box");
		clear(box);
		if (!isObject(backup) || backup["streamhub-backup"] !== 1 || !isObject(backup.files)) {
			box.appendChild(el("div", fileName + " is not a Streamhub backup file.", "sh-alert sh-alert-bad"));
			return;
		}
		box.appendChild(facts([["File", fileName], ["Created", str(backup.created).replace("T", " ") || "–"],
			["Streamhub", str(backup.version) || "–"], ["Instance", str(backup.instance) || "–"]]));
		var list = table(["Restore", "File", "In the backup"]), boxes = [];
		["config", "apps", "users", "news"].forEach(function (key) {
			var entry = isObject(backup.files[key]) ? backup.files[key] : {}, has = typeof entry.text === "string", row = el("tr");
			var check = el("input");
			check.type = "checkbox";
			check.value = key;
			check.checked = has;
			check.disabled = !has;
			check.setAttribute("aria-label", "Restore " + FILE_LABELS[key]);
			boxes.push(check);
			cell(row, "Restore", check);
			var name = el("div", null, "sh-app-cell");
			name.appendChild(el("b", FILE_LABELS[key]));
			if (entry.name) { name.appendChild(el("small", entry.name)); }
			cell(row, "File", name);
			cell(row, "In the backup", has ? size(new Blob([entry.text]).size) : "not included", has ? "" : "sh-muted");
			list.body.appendChild(row);
		});
		box.appendChild(list.node);
		var bar = el("div", null, "sh-editor-actions"), go = el("button", null, "btn btn-sm sh-btn-danger");
		go.type = "button";
		go.appendChild(el("i", null, "fa fa-upload"));
		go.appendChild(document.createTextNode(" Restore the chosen files"));
		bar.appendChild(go);
		box.appendChild(bar);
		var result = el("div");
		box.appendChild(result);
		go.addEventListener("click", function () {
			var chosen = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
			clear(result);
			if (!chosen.length) { restoreResult(result, "Choose at least one file.", true); return; }
			if (!window.confirm("Replace " + chosen.map(function (k) { return FILE_LABELS[k]; }).join(", ") + " with the backup's?")) { return; }
			go.disabled = true;
			A.api("POST", "/api/admin/restore", {backup: backup, files: chosen}).then(function (r) {
				restoreResult(result, r.ok ? r.message : r.error, !r.ok, r.restart);
				if (r.ok) { files = {}; settingsDirty = false; docker = null; }
			}).catch(function (error) { restoreResult(result, error.message, true); })
				.then(function () { go.disabled = false; });
		});
	}
	$("restore-file").addEventListener("change", function () {
		var file = this.files[0];
		this.value = "";
		if (!file) { return; }
		var reader = new FileReader();
		reader.onload = function () {
			var backup = null;
			try { backup = JSON.parse(reader.result); } catch (e) { backup = null; }
			showRestore(backup, file.name);
		};
		reader.readAsText(file);
	});

	// -- tabs: each editor reloads its file when its tab opens --
	var VIEWS = {apps: showApps, users: showUsers, news: showNews, settings: showSettings, docker: showDocker, static: showStatic};
	document.addEventListener("sh-tab", function (event) { if (VIEWS[event.detail]) { VIEWS[event.detail](); } });
	var active = document.querySelector(".sh-tab-panel.active");
	if (active && VIEWS[active.getAttribute("data-panel")]) { VIEWS[active.getAttribute("data-panel")](); }
})();
