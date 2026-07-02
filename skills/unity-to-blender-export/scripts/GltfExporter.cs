using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;
using System.Linq;
using System.Text;
using GLTFast;
using GLTFast.Export;

public static class GltfExporter
{
    /// <summary>验证用:创建一个立方体导成 glb。</summary>
    public static void ExportCube()
    {
        var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
        go.name = "TestCube";
        var r = go.GetComponent<Renderer>();
        if (r) { var m = new Material(Shader.Find("Standard")); m.color = Color.green; r.sharedMaterial = m; }
        RunExport(new[] { go }, "/shared/gta-resources/unity_gltf_proj/Export/test_cube.glb");
    }

    static int RendererCount(GameObject g) => g.GetComponentsInChildren<Renderer>(true).Length;

    /// <summary>打印场景层级(根+两级),含 renderer 数,便于挑单栋楼。</summary>
    static void DumpHierarchy(GameObject[] roots)
    {
        var sb = new StringBuilder();
        sb.AppendLine("HIER_BEGIN");
        foreach (var root in roots.OrderByDescending(RendererCount))
        {
            sb.AppendLine($"ROOT | {root.name} | rend={RendererCount(root)} | children={root.transform.childCount}");
            foreach (Transform c in root.transform)
            {
                sb.AppendLine($"  L1 | {c.name} | rend={RendererCount(c.gameObject)} | children={c.childCount}");
                foreach (Transform gc in c)
                    sb.AppendLine($"    L2 | {gc.name} | rend={RendererCount(gc.gameObject)} | children={gc.childCount}");
            }
        }
        sb.AppendLine("HIER_END");
        Debug.Log(sb.ToString());
    }

    /// <summary>
    /// 导出场景。env:
    ///   EXPORT_SCENE  场景路径(必填)
    ///   EXPORT_OUT    输出 glb(dumpOnly 时可空)
    ///   EXPORT_ROOT   可选:逗号分隔名字,在整棵树按名字找,只导这些节点(不限根级)
    ///   DUMP_ONLY     "1" = 只打印层级不导出
    /// </summary>
    public static void ExportScene()
    {
        var scenePath = System.Environment.GetEnvironmentVariable("EXPORT_SCENE");
        var outPath = System.Environment.GetEnvironmentVariable("EXPORT_OUT");
        var rootFilter = System.Environment.GetEnvironmentVariable("EXPORT_ROOT");
        var dumpOnly = System.Environment.GetEnvironmentVariable("DUMP_ONLY") == "1";
        Debug.Log($"[GltfExporter] scene={scenePath} out={outPath} root={rootFilter} dumpOnly={dumpOnly}");
        if (string.IsNullOrEmpty(scenePath) || (string.IsNullOrEmpty(outPath) && !dumpOnly))
        {
            Debug.LogError("[GltfExporter] 需 EXPORT_SCENE 且(EXPORT_OUT 或 DUMP_ONLY=1)");
            EditorApplication.Exit(2); return;
        }
        var scene = EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
        // 激活隐藏(inactive)对象——否则 glTFast 只导 active,漏掉高山/悬崖/隐藏楼等
        if (System.Environment.GetEnvironmentVariable("EXPORT_INCLUDE_INACTIVE") == "1")
        {
            int activated = 0;
            var allT = Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            foreach (var t in allT)
                if (!t.gameObject.activeSelf) { t.gameObject.SetActive(true); activated++; }
            Debug.Log($"[GltfExporter] EXPORT_INCLUDE_INACTIVE: 激活了 {activated} 个隐藏对象");
        }
        var roots = scene.GetRootGameObjects();
        DumpHierarchy(roots);

        if (dumpOnly) { Debug.Log("DUMP_DONE"); EditorApplication.Exit(0); return; }

        GameObject[] targets = roots;
        if (!string.IsNullOrEmpty(rootFilter))
        {
            var pick = System.Environment.GetEnvironmentVariable("EXPORT_PICK"); // "max" = 只取 renderer 最多的一个
            var norm = System.Environment.GetEnvironmentVariable("EXPORT_NORM") == "1"; // 归一化: 去掉 " (N)" 后缀再比
            System.Func<string,string> N = s => norm ? System.Text.RegularExpressions.Regex.Replace(s, @"\s*\(\d+\)\s*$", "").Trim() : s;
            var names = new System.Collections.Generic.HashSet<string>(rootFilter.Split(',').Select(x => N(x)));
            var all = Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            // 只保留有 renderer 的匹配节点(场景里同名空节点/缺引用节点剔掉)
            var matched = all.Where(t => names.Contains(N(t.name)) && RendererCount(t.gameObject) > 0)
                             .Select(t => t.gameObject);
            if (pick == "max")
                matched = matched.OrderByDescending(g => RendererCount(g)).Take(1);
            targets = matched.ToArray();
            Debug.Log($"[GltfExporter] 名字匹配(含renderer,pick={pick})到 {targets.Length} 个节点: {string.Join(",", targets.Select(t=>$"{t.name}(r={RendererCount(t)})"))}");
        }
        RunExport(targets, outPath);
    }

    /// <summary>
    /// 批量导出多个建筑 archetype。env:
    ///   EXPORT_SCENE       场景路径
    ///   EXPORT_BATCH_NAMES 逗号分隔的节点名(每个取 renderer 最多的实例)
    ///   EXPORT_BATCH_DIR   输出目录(每个 archetype 一个 <name>.glb)
    /// </summary>
    public static async void ExportBatch()
    {
        try
        {
            var scenePath = System.Environment.GetEnvironmentVariable("EXPORT_SCENE");
            var namesCsv = System.Environment.GetEnvironmentVariable("EXPORT_BATCH_NAMES");
            var dir = System.Environment.GetEnvironmentVariable("EXPORT_BATCH_DIR");
            if (string.IsNullOrEmpty(scenePath) || string.IsNullOrEmpty(namesCsv) || string.IsNullOrEmpty(dir))
            { Debug.LogError("[GltfExporter] ExportBatch 需 EXPORT_SCENE / EXPORT_BATCH_NAMES / EXPORT_BATCH_DIR"); EditorApplication.Exit(2); return; }
            EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
            System.IO.Directory.CreateDirectory(dir);
            var all = Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            int ok = 0, fail = 0;
            foreach (var name in namesCsv.Split(','))
            {
                var g = all.Where(t => t.name == name && RendererCount(t.gameObject) > 0)
                           .OrderByDescending(t => RendererCount(t.gameObject))
                           .Select(t => t.gameObject).FirstOrDefault();
                if (g == null) { Debug.Log($"BATCH_SKIP {name} (无renderer节点)"); fail++; continue; }
                var outPath = System.IO.Path.Combine(dir, name + ".glb");
                try
                {
                    var settings = new ExportSettings { Format = GltfFormat.Binary, FileConflictResolution = FileConflictResolution.Overwrite, ComponentMask = ~(ComponentType.Camera | ComponentType.Animation) };
                    var export = new GameObjectExport(settings);
                    export.AddScene(new[] { g }, "scene");
                    bool r = await export.SaveToFileAndDispose(outPath);
                    Debug.Log(r ? $"BATCH_OK {name} r={RendererCount(g)} -> {outPath}" : $"BATCH_FAIL {name}");
                    if (r) ok++; else fail++;
                }
                catch (System.Exception e) { Debug.LogError($"BATCH_FAIL {name}: {e.Message}"); fail++; }
            }
            Debug.Log($"BATCH_DONE ok={ok} fail={fail}");
            EditorApplication.Exit(0);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] ExportBatch 异常: " + e); EditorApplication.Exit(1); }
    }

    static string Norm(string s) => System.Text.RegularExpressions.Regex.Replace(s, @"\s*\(\d+\)\s*$", "").Trim();

    static int EnableReadable()
    {
        var guids = AssetDatabase.FindAssets("t:Model");
        int reimp = 0, n = 0;
        AssetDatabase.StartAssetEditing();
        try {
            foreach (var g in guids) {
                var path = AssetDatabase.GUIDToAssetPath(g);
                var imp = AssetImporter.GetAtPath(path) as ModelImporter;
                if (imp != null && !imp.isReadable) { imp.isReadable = true; imp.SaveAndReimport(); reimp++; }
                if ((++n) % 1000 == 0) Debug.Log($"READABLE_PROGRESS {n}/{guids.Length} reimported={reimp}");
            }
        } finally { AssetDatabase.StopAssetEditing(); }
        AssetDatabase.Refresh();
        Debug.Log($"READABLE_DONE reimported={reimp}/{guids.Length}");
        return reimp;
    }

    /// <summary>
    /// 同会话:开 Read/Write 重导入 + 导出整个场景为一个 glb(所有根节点,激活后导)。
    /// env: EXPORT_SCENE / EXPORT_OUT
    /// </summary>
    public static async void ReadableExportScene()
    {
        try
        {
            var scenePath = System.Environment.GetEnvironmentVariable("EXPORT_SCENE");
            var outPath = System.Environment.GetEnvironmentVariable("EXPORT_OUT");
            if (string.IsNullOrEmpty(scenePath) || string.IsNullOrEmpty(outPath))
            { Debug.LogError("[GltfExporter] 需 EXPORT_SCENE / EXPORT_OUT"); EditorApplication.Exit(2); return; }
            EnableReadable();
            EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
            var roots = UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects();
            DumpHierarchy(roots);
            // 激活所有根(inactive 的备选内容也一并导,方便整体查看)
            foreach (var r in roots) r.SetActive(true);
            System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outPath));
            var settings = new ExportSettings { Format = GltfFormat.Binary, FileConflictResolution = FileConflictResolution.Overwrite, ComponentMask = ~(ComponentType.Camera | ComponentType.Animation) };
            var export = new GameObjectExport(settings);
            export.AddScene(roots, "scene");
            bool ok = await export.SaveToFileAndDispose(outPath);
            Debug.Log(ok ? $"GLTF_EXPORT_OK -> {outPath}" : "GLTF_EXPORT_FAIL");
            EditorApplication.Exit(ok ? 0 : 1);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] ReadableExportScene 异常: " + e); EditorApplication.Exit(1); }
    }

    /// <summary>
    /// 同会话:先给所有模型开 Read/Write 重导入(解决 glTFast 多导出 isReadable + fresh-session 不实例化),
    /// 再批量导出建筑。env:
    ///   EXPORT_SCENE / EXPORT_BATCH_NAMES(逗号分隔) / EXPORT_BATCH_DIR
    /// </summary>
    public static async void ImportReadableAndBatch()
    {
        try
        {
            var scenePath = System.Environment.GetEnvironmentVariable("EXPORT_SCENE");
            var namesCsv = System.Environment.GetEnvironmentVariable("EXPORT_BATCH_NAMES");
            var dir = System.Environment.GetEnvironmentVariable("EXPORT_BATCH_DIR");
            if (string.IsNullOrEmpty(scenePath) || string.IsNullOrEmpty(namesCsv) || string.IsNullOrEmpty(dir))
            { Debug.LogError("[GltfExporter] 需 EXPORT_SCENE / EXPORT_BATCH_NAMES / EXPORT_BATCH_DIR"); EditorApplication.Exit(2); return; }

            // 1) 全模型开 Read/Write 重导入
            var guids = AssetDatabase.FindAssets("t:Model");
            Debug.Log($"READABLE_START models={guids.Length}");
            int reimp = 0, n = 0;
            AssetDatabase.StartAssetEditing();
            try {
                foreach (var g in guids) {
                    var path = AssetDatabase.GUIDToAssetPath(g);
                    var imp = AssetImporter.GetAtPath(path) as ModelImporter;
                    if (imp != null && !imp.isReadable) { imp.isReadable = true; imp.SaveAndReimport(); reimp++; }
                    if ((++n) % 500 == 0) Debug.Log($"READABLE_PROGRESS {n}/{guids.Length} reimported={reimp}");
                }
            } finally { AssetDatabase.StopAssetEditing(); }
            AssetDatabase.Refresh();
            Debug.Log($"READABLE_DONE reimported={reimp}");

            // 2) 开场景(同会话,建筑全部实例化)
            EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
            System.IO.Directory.CreateDirectory(dir);
            var all = Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);

            // 3) 逐 archetype 归一化匹配 + renderer 最多 + 导出
            int ok = 0, fail = 0;
            foreach (var raw in namesCsv.Split(','))
            {
                var target = Norm(raw);
                var g = all.Where(t => Norm(t.name) == target && RendererCount(t.gameObject) > 0)
                           .OrderByDescending(t => RendererCount(t.gameObject))
                           .Select(t => t.gameObject).FirstOrDefault();
                if (g == null) { Debug.Log($"BATCH_SKIP {target} (无renderer节点)"); fail++; continue; }
                // demo 场景里部分楼被禁用(inactive) -> glTFast 会跳过其 mesh。导出前激活本体+全部祖先。
                for (var t = g.transform; t != null; t = t.parent) t.gameObject.SetActive(true);
                var outPath = System.IO.Path.Combine(dir, target + ".glb");
                try {
                    var settings = new ExportSettings { Format = GltfFormat.Binary, FileConflictResolution = FileConflictResolution.Overwrite, ComponentMask = ~(ComponentType.Camera | ComponentType.Animation) };
                    var export = new GameObjectExport(settings);
                    export.AddScene(new[] { g }, "scene");
                    bool r = await export.SaveToFileAndDispose(outPath);
                    Debug.Log(r ? $"BATCH_OK {target} r={RendererCount(g)} -> {outPath}" : $"BATCH_FAIL {target}");
                    if (r) ok++; else fail++;
                } catch (System.Exception e) { Debug.LogError($"BATCH_FAIL {target}: {e.Message}"); fail++; }
            }
            Debug.Log($"BATCH_DONE ok={ok} fail={fail}");
            EditorApplication.Exit(0);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] ImportReadableAndBatch 异常: " + e); EditorApplication.Exit(1); }
    }

    // ---------- 新管线:fbx→prefab→scene 一比一回 Blender ----------

    static string JsonStr(string s) =>
        "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n") + "\"";

    static string HierPath(Transform t)
    {
        var parts = new System.Collections.Generic.List<string>();
        for (var c = t; c != null; c = c.parent) parts.Add(c.name);
        parts.Reverse();
        return string.Join("/", parts);
    }

    static string Mat16(Matrix4x4 m) => string.Join(",", new[] {
        m.m00, m.m01, m.m02, m.m03, m.m10, m.m11, m.m12, m.m13,
        m.m20, m.m21, m.m22, m.m23, m.m30, m.m31, m.m32, m.m33
    }.Select(f => f.ToString("R")));

    /// <summary>
    /// 场景实例清单:每个最外层 prefab 实例根一条(实例名/层级路径/源 prefab 路径+GUID/
    /// Unity 世界矩阵/激活态/override 概况),外加不属于任何 prefab 的散 renderer。
    /// env: EXPORT_SCENES(逗号分隔场景路径) EXPORT_MANIFEST_DIR(输出目录)
    /// </summary>
    public static void ExportSceneManifests()
    {
        try
        {
            var scenesCsv = System.Environment.GetEnvironmentVariable("EXPORT_SCENES");
            var outDir = System.Environment.GetEnvironmentVariable("EXPORT_MANIFEST_DIR");
            if (string.IsNullOrEmpty(scenesCsv) || string.IsNullOrEmpty(outDir))
            { Debug.LogError("[GltfExporter] 需 EXPORT_SCENES / EXPORT_MANIFEST_DIR"); EditorApplication.Exit(2); return; }
            System.IO.Directory.CreateDirectory(outDir);

            foreach (var scenePath in scenesCsv.Split(','))
            {
                var scene = EditorSceneManager.OpenScene(scenePath.Trim(), OpenSceneMode.Single);
                var all = Object.FindObjectsByType<Transform>(FindObjectsInactive.Include, FindObjectsSortMode.None);

                var sb = new StringBuilder();
                sb.Append("{\n").Append("\"scene\": ").Append(JsonStr(scenePath.Trim())).Append(",\n");
                sb.Append("\"instances\": [\n");
                int nInst = 0, nOverride = 0;
                bool first = true;
                foreach (var t in all)
                {
                    var go = t.gameObject;
                    if (!PrefabUtility.IsAnyPrefabInstanceRoot(go)) continue;
                    if (!PrefabUtility.IsOutermostPrefabInstanceRoot(go)) continue;
                    var assetPath = PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(go);
                    // 精确 diff:实例内部树 vs prefab 资产树(变换/激活/材质/增删),不靠 PropertyModifications 噪声
                    var mods = new StringBuilder();
                    int nMods = DiffInstanceVsAsset(t, assetPath, mods);
                    if (nMods > 0) nOverride++;
                    if (!first) sb.Append(",\n");
                    first = false;
                    sb.Append("{\"name\": ").Append(JsonStr(go.name))
                      .Append(", \"path\": ").Append(JsonStr(HierPath(t)))
                      .Append(", \"prefab\": ").Append(JsonStr(assetPath))
                      .Append(", \"guid\": ").Append(JsonStr(AssetDatabase.AssetPathToGUID(assetPath)))
                      .Append(", \"active\": ").Append(go.activeInHierarchy ? "true" : "false")
                      .Append(", \"matrix\": [").Append(Mat16(t.localToWorldMatrix)).Append("]")
                      .Append(", \"mods\": [").Append(mods).Append("]}");
                    nInst++;
                }
                sb.Append("\n],\n\"loose\": [\n");
                first = true;
                int nLoose = 0;
                foreach (var r in Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None))
                {
                    if (PrefabUtility.GetNearestPrefabInstanceRoot(r.gameObject) != null) continue;
                    var mf = r.GetComponent<MeshFilter>();
                    var meshPath = mf && mf.sharedMesh ? AssetDatabase.GetAssetPath(mf.sharedMesh) : "";
                    if (!first) sb.Append(",\n");
                    first = false;
                    sb.Append("{\"name\": ").Append(JsonStr(r.gameObject.name))
                      .Append(", \"path\": ").Append(JsonStr(HierPath(r.transform)))
                      .Append(", \"mesh_asset\": ").Append(JsonStr(meshPath))
                      .Append(", \"mesh\": ").Append(JsonStr(mf && mf.sharedMesh ? mf.sharedMesh.name : ""))
                      .Append(", \"active\": ").Append(r.gameObject.activeInHierarchy ? "true" : "false")
                      .Append(", \"matrix\": [").Append(Mat16(r.transform.localToWorldMatrix)).Append("]}");
                    nLoose++;
                }
                sb.Append("\n]\n}\n");
                var outPath = System.IO.Path.Combine(outDir,
                    System.IO.Path.GetFileNameWithoutExtension(scenePath.Trim()) + ".manifest.json");
                System.IO.File.WriteAllText(outPath, sb.ToString());
                Debug.Log($"MANIFEST_OK {scene.name} instances={nInst} overrides={nOverride} loose={nLoose} -> {outPath}");
            }
            EditorApplication.Exit(0);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] ExportSceneManifests 异常: " + e); EditorApplication.Exit(1); }
    }

    static string RelPath(Transform t, Transform root)
    {
        var parts = new System.Collections.Generic.List<string>();
        for (var c = t; c != null && c != root; c = c.parent) parts.Add(c.name);
        parts.Reverse();
        return string.Join("/", parts);
    }

    /// <summary>路径段:同名兄弟按局部坐标(round 1e-3)排序加 #k 消歧(与 Blender 侧约定一致)。</summary>
    static string Seg(Transform c)
    {
        var p = c.parent;
        if (p == null) return c.name;
        var same = new System.Collections.Generic.List<Transform>();
        foreach (Transform s in p) if (s.name == c.name) same.Add(s);
        if (same.Count == 1) return c.name;
        System.Func<Transform, (double, double, double)> key = x => (
            System.Math.Round((double)x.localPosition.x, 3),
            System.Math.Round((double)x.localPosition.y, 3),
            System.Math.Round((double)x.localPosition.z, 3));
        same.Sort((a, b) => {
            int cmp = key(a).CompareTo(key(b));
            return cmp != 0 ? cmp : a.GetSiblingIndex().CompareTo(b.GetSiblingIndex());
        });
        return c.name + "#" + same.IndexOf(c);
    }

    /// <summary>资产树内的消歧相对路径(root 不含)。</summary>
    static string DPath(Transform t, Transform root)
    {
        var parts = new System.Collections.Generic.List<string>();
        for (var c = t; c != null && c != root; c = c.parent) parts.Add(Seg(c));
        parts.Reverse();
        return string.Join("/", parts);
    }

    // prefab 资产路径映射缓存:资产 Transform → 纯净实例化后的消歧路径(与 prefab glb 一致)。
    // 嵌套 prefab 里 GetCorrespondingObjectFromSource 会指到子 prefab 资产,直接 DPath 会缺前缀,
    // 所以用「纯净实例」把 corresponding → 完整路径 一次性建表。
    static System.Collections.Generic.Dictionary<string, System.Collections.Generic.Dictionary<Object, string>> _pathMaps
        = new System.Collections.Generic.Dictionary<string, System.Collections.Generic.Dictionary<Object, string>>();

    static System.Collections.Generic.Dictionary<Object, string> AssetPathMap(string assetPath)
    {
        if (_pathMaps.TryGetValue(assetPath, out var got)) return got;
        var map = new System.Collections.Generic.Dictionary<Object, string>();
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
        if (prefab != null)
        {
            var inst = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            foreach (var x in inst.GetComponentsInChildren<Transform>(true))
            {
                // 键 = 最深源对象:场景实例与纯净实例的 corresponding 可能解析到不同嵌套层,
                // 归一到 original source 才对得上。嵌套复用导致的碰撞取首见(深度优先序,确定性)。
                var key = PrefabUtility.GetCorrespondingObjectFromOriginalSource(x);
                if (key != null && !map.ContainsKey(key)) map[key] = DPath(x, inst.transform);
            }
            Object.DestroyImmediate(inst);
        }
        _pathMaps[assetPath] = map;
        return map;
    }

    /// <summary>
    /// 实例内部树 vs prefab 资产精确 diff(跳过根变换——那是实例摆放本身)。
    /// 输出 mods JSON 片段,返回条数。类型:transform(局部矩阵)/active/materials/added/removed。
    /// tpath 一律用【资产侧】消歧路径(AssetPathMap 查表,与 prefab glb 一致)。
    /// </summary>
    static int DiffInstanceVsAsset(Transform root, string assetPath, StringBuilder sb)
    {
        int n = 0;
        void Emit(string type, string rel, string extra)
        {
            if (n > 0) sb.Append(",");
            sb.Append("{\"type\": ").Append(JsonStr(type)).Append(", \"tpath\": ").Append(JsonStr(rel));
            if (extra != null) sb.Append(", ").Append(extra);
            sb.Append("}");
            n++;
        }
        var pathMap = AssetPathMap(assetPath);
        // 实例内新增的子树(含嵌套 prefab 实例,如塞进车里的角色):整棵记一条 added,不逐节点 diff
        var addedRoots = new System.Collections.Generic.HashSet<Transform>();
        try
        {
            foreach (var ag in PrefabUtility.GetAddedGameObjects(root.gameObject))
                if (ag.instanceGameObject != null) addedRoots.Add(ag.instanceGameObject.transform);
        }
        catch (System.Exception) { }
        bool UnderAdded(Transform x)
        { for (var c = x; c != null && c != root; c = c.parent) if (addedRoots.Contains(c)) return true; return false; }

        foreach (var t in root.GetComponentsInChildren<Transform>(true))
        {
            string ParentRel(Transform x)
            {
                var pt = x.parent;
                if (pt == null || pt == root) return "";
                var pk = PrefabUtility.GetCorrespondingObjectFromOriginalSource(pt);
                return pk != null && pathMap.TryGetValue(pk, out var pp) ? pp : "!" + RelPath(pt, root);
            }
            if (addedRoots.Contains(t))
            {
                var ap2 = PrefabUtility.IsAnyPrefabInstanceRoot(t.gameObject)
                    ? PrefabUtility.GetPrefabAssetPathOfNearestInstanceRoot(t.gameObject) : "";
                Emit("added", ParentRel(t),
                    "\"name\": " + JsonStr(t.name) + ", \"prefab\": " + JsonStr(ap2) +
                    ", \"matrix\": [" + Mat16(Matrix4x4.TRS(t.localPosition, t.localRotation, t.localScale)) + "]");
                continue;
            }
            if (UnderAdded(t)) continue;
            var src = PrefabUtility.GetCorrespondingObjectFromSource(t);
            if (src == null)
            {
                if (t != root) Emit("added", ParentRel(t),
                    "\"name\": " + JsonStr(t.name) + ", \"prefab\": \"\", \"matrix\": [" + Mat16(Matrix4x4.TRS(t.localPosition, t.localRotation, t.localScale)) + "]");
                continue;
            }
            var okey = PrefabUtility.GetCorrespondingObjectFromOriginalSource(t);
            if (okey == null || !pathMap.TryGetValue(okey, out var rel)) rel = "!" + RelPath(t, root); // ! = 查表失败
            if (t != root)
            {
                bool moved = (t.localPosition - src.localPosition).sqrMagnitude > 1e-10f ||
                             Quaternion.Angle(t.localRotation, src.localRotation) > 1e-3f ||
                             (t.localScale - src.localScale).sqrMagnitude > 1e-10f;
                if (moved) Emit("transform", rel, "\"matrix\": [" + Mat16(Matrix4x4.TRS(t.localPosition, t.localRotation, t.localScale)) + "]");
            }
            var srcGo = src.gameObject;
            if (t.gameObject.activeSelf != srcGo.activeSelf)
                Emit("active", rel, "\"value\": " + (t.gameObject.activeSelf ? "true" : "false"));
            var r = t.GetComponent<Renderer>(); var sr = srcGo.GetComponent<Renderer>();
            if (r != null && sr != null)
            {
                var a = r.sharedMaterials; var b = sr.sharedMaterials;
                bool diff = a.Length != b.Length;
                for (int i = 0; !diff && i < a.Length; i++) diff = a[i] != b[i];
                if (diff) Emit("materials", rel,
                    "\"value\": [" + string.Join(",", a.Select(m => JsonStr(m ? m.name : ""))) + "]");
            }
        }
        try
        {
            foreach (var rm in PrefabUtility.GetRemovedGameObjects(root.gameObject))
            {
                if (rm.assetGameObject == null) { Emit("removed", "?", null); continue; }
                var rkey = PrefabUtility.GetCorrespondingObjectFromOriginalSource(rm.assetGameObject.transform)
                           ?? rm.assetGameObject.transform;
                Emit("removed", pathMap.TryGetValue(rkey, out var rp)
                    ? rp : "!" + rm.assetGameObject.name, null);
            }
        }
        catch (System.Exception) { }
        return n;
    }

    /// <summary>
    /// 批量 prefab → glb(单次会话)。每个 prefab 实例化后按资产镜像路径导出,
    /// 保留内部 GameObject 树/名字/材质。env:
    ///   EXPORT_PREFAB_LIST  文本文件,每行一个 prefab 资产路径
    ///   EXPORT_PREFAB_DIR   输出根目录(镜像 Assets 下相对路径,.prefab→.glb)
    ///   EXPORT_READABLE     "1" = 先给全部模型开 Read/Write
    /// </summary>
    public static async void ExportPrefabs()
    {
        try
        {
            var listPath = System.Environment.GetEnvironmentVariable("EXPORT_PREFAB_LIST");
            var dir = System.Environment.GetEnvironmentVariable("EXPORT_PREFAB_DIR");
            if (string.IsNullOrEmpty(listPath) || string.IsNullOrEmpty(dir))
            { Debug.LogError("[GltfExporter] 需 EXPORT_PREFAB_LIST / EXPORT_PREFAB_DIR"); EditorApplication.Exit(2); return; }
            if (System.Environment.GetEnvironmentVariable("EXPORT_READABLE") == "1") EnableReadable();

            var paths = System.IO.File.ReadAllLines(listPath)
                .Select(l => l.Trim()).Where(l => l.Length > 0 && !l.StartsWith("#")).ToArray();
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            int ok = 0, fail = 0, n = 0;
            foreach (var assetPath in paths)
            {
                n++;
                var rel = assetPath.StartsWith("Assets/") ? assetPath.Substring(7) : assetPath;
                var outPath = System.IO.Path.Combine(dir, System.IO.Path.ChangeExtension(rel, ".glb"));
                GameObject inst = null;
                try
                {
                    var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
                    if (prefab == null) { Debug.Log($"PREFAB_FAIL {assetPath} (加载失败)"); fail++; continue; }
                    inst = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
                    inst.name = prefab.name; // 去 (Clone)
                    // 根节点 TRS 归零:场景实例会整体替换根变换(manifest 的 matrix 就是它),
                    // 导出内容只保留根以下的局部链,否则拼装时双重变换
                    inst.transform.localPosition = Vector3.zero;
                    inst.transform.localRotation = Quaternion.identity;
                    inst.transform.localScale = Vector3.one;
                    // glTFast 只导 active 节点:先记录默认禁用清单(sidecar),再全激活导出,
                    // Blender 侧按 sidecar 隐藏——这样实例级 active:true 的 mod 才有对象可用
                    var inactive = inst.GetComponentsInChildren<Transform>(true)
                        .Where(x => !x.gameObject.activeSelf && x != inst.transform)
                        .Select(x => DPath(x, inst.transform)).ToArray();
                    foreach (var x in inst.GetComponentsInChildren<Transform>(true))
                        x.gameObject.SetActive(true);
                    System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outPath) ?? ".");
                    if (inactive.Length > 0)
                        System.IO.File.WriteAllText(
                            System.IO.Path.Combine(System.IO.Path.GetDirectoryName(outPath) ?? ".",
                                System.IO.Path.GetFileNameWithoutExtension(outPath) + ".inactive.json"),
                            "[" + string.Join(",", inactive.Select(JsonStr)) + "]");
                    System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outPath));
                    var settings = new ExportSettings { Format = GltfFormat.Binary, FileConflictResolution = FileConflictResolution.Overwrite, ComponentMask = ~(ComponentType.Camera | ComponentType.Animation) };
                    var export = new GameObjectExport(settings);
                    export.AddScene(new[] { inst }, prefab.name);
                    bool r = await export.SaveToFileAndDispose(outPath);
                    if (r) { ok++; Debug.Log($"PREFAB_OK {assetPath}"); }
                    else { fail++; Debug.Log($"PREFAB_FAIL {assetPath}"); }
                }
                catch (System.Exception e) { fail++; Debug.LogError($"PREFAB_FAIL {assetPath}: {e.Message}"); }
                finally { if (inst != null) Object.DestroyImmediate(inst); }
                if (n % 200 == 0) Debug.Log($"PREFAB_PROGRESS {n}/{paths.Length} ok={ok} fail={fail}");
            }
            Debug.Log($"PREFAB_DONE ok={ok} fail={fail} total={paths.Length}");
            EditorApplication.Exit(fail == 0 ? 0 : 3);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] ExportPrefabs 异常: " + e); EditorApplication.Exit(1); }
    }

    /// <summary>
    /// 导出场景「散件」:不属于任何 prefab 实例的 renderer 节点,按场景各出一个 glb
    /// (世界坐标烘焙:导出前把节点搬到临时根下保持世界变换)。
    /// env: EXPORT_SCENES / EXPORT_LOOSE_DIR
    /// </summary>
    public static async void ExportLooseNodes()
    {
        try
        {
            var scenesCsv = System.Environment.GetEnvironmentVariable("EXPORT_SCENES");
            var outDir = System.Environment.GetEnvironmentVariable("EXPORT_LOOSE_DIR");
            if (string.IsNullOrEmpty(scenesCsv) || string.IsNullOrEmpty(outDir))
            { Debug.LogError("[GltfExporter] 需 EXPORT_SCENES / EXPORT_LOOSE_DIR"); EditorApplication.Exit(2); return; }
            System.IO.Directory.CreateDirectory(outDir);
            foreach (var scenePath in scenesCsv.Split(','))
            {
                var scene = EditorSceneManager.OpenScene(scenePath.Trim(), OpenSceneMode.Single);
                var loose = Object.FindObjectsByType<Renderer>(FindObjectsInactive.Include, FindObjectsSortMode.None)
                    .Where(r => PrefabUtility.GetNearestPrefabInstanceRoot(r.gameObject) == null)
                    .Select(r => r.gameObject).ToArray();
                if (loose.Length == 0) { Debug.Log($"LOOSE_OK {scene.name} n=0 (跳过)"); continue; }
                var holder = new GameObject("SceneOnly");
                foreach (var g in loose)
                {
                    g.SetActive(true);
                    for (var t = g.transform; t != null; t = t.parent) t.gameObject.SetActive(true);
                    g.transform.SetParent(holder.transform, true); // 保持世界变换
                }
                var outPath = System.IO.Path.Combine(outDir, System.IO.Path.GetFileNameWithoutExtension(scenePath.Trim()) + "_loose.glb");
                var settings = new ExportSettings { Format = GltfFormat.Binary, FileConflictResolution = FileConflictResolution.Overwrite, ComponentMask = ~(ComponentType.Camera | ComponentType.Animation) };
                var export = new GameObjectExport(settings);
                export.AddScene(new[] { holder }, "loose");
                bool ok = await export.SaveToFileAndDispose(outPath);
                Debug.Log($"LOOSE_OK {scene.name} n={loose.Length} saved={ok} -> {outPath}");
            }
            EditorApplication.Exit(0);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] ExportLooseNodes 异常: " + e); EditorApplication.Exit(1); }
    }

    /// <summary>
    /// 材质调色板:项目全部 .mat 各挂一个 cube,导出一个 glb。
    /// 场景实例的材质 override 可能引用「无 prefab 默认使用」的材质,库里必须有全集才能按名字换。
    /// env: EXPORT_OUT
    /// </summary>
    public static async void ExportMaterialPalette()
    {
        try
        {
            var outPath = System.Environment.GetEnvironmentVariable("EXPORT_OUT");
            if (string.IsNullOrEmpty(outPath)) { Debug.LogError("需 EXPORT_OUT"); EditorApplication.Exit(2); return; }
            var guids = AssetDatabase.FindAssets("t:Material", new[] { "Assets/BlendPoly Modular City" });
            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var holder = new GameObject("MaterialPalette");
            int n = 0;
            foreach (var g in guids)
            {
                var mat = AssetDatabase.LoadAssetAtPath<Material>(AssetDatabase.GUIDToAssetPath(g));
                if (mat == null) continue;
                var cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
                cube.name = "PAL_" + mat.name;
                cube.transform.SetParent(holder.transform, false);
                cube.transform.localPosition = new Vector3(n * 2.5f, 0, 0);
                cube.GetComponent<Renderer>().sharedMaterial = mat;
                n++;
            }
            System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outPath));
            var settings = new ExportSettings { Format = GltfFormat.Binary, FileConflictResolution = FileConflictResolution.Overwrite, ComponentMask = ~(ComponentType.Camera | ComponentType.Animation) };
            var export = new GameObjectExport(settings);
            export.AddScene(new[] { holder }, "palette");
            bool ok = await export.SaveToFileAndDispose(outPath);
            Debug.Log($"PALETTE_OK mats={n} saved={ok} -> {outPath}");
            EditorApplication.Exit(ok ? 0 : 1);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] ExportMaterialPalette 异常: " + e); EditorApplication.Exit(1); }
    }

    /// <summary>
    /// 指定机位截图(与 Blender render_snapshot 对拍用)。需 batchmode【不带 -nographics】。
    /// env: EXPORT_SCENE / EXPORT_OUT / CAM_POS "x,y,z" / CAM_LOOK "x,y,z" / CAM_FOV(垂直度数) / CAM_RES "1600x1000"
    /// </summary>
    public static void CaptureView()
    {
        try
        {
            var scenePath = System.Environment.GetEnvironmentVariable("EXPORT_SCENE");
            var outPath = System.Environment.GetEnvironmentVariable("EXPORT_OUT");
            var posS = System.Environment.GetEnvironmentVariable("CAM_POS");
            var lookS = System.Environment.GetEnvironmentVariable("CAM_LOOK");
            var fovS = System.Environment.GetEnvironmentVariable("CAM_FOV") ?? "25.4";
            var resS = System.Environment.GetEnvironmentVariable("CAM_RES") ?? "1600x1000";
            if (string.IsNullOrEmpty(scenePath) || string.IsNullOrEmpty(outPath) || string.IsNullOrEmpty(posS) || string.IsNullOrEmpty(lookS))
            { Debug.LogError("需 EXPORT_SCENE/EXPORT_OUT/CAM_POS/CAM_LOOK"); EditorApplication.Exit(2); return; }
            Vector3 P(string s) { var a = s.Split(','); return new Vector3(float.Parse(a[0]), float.Parse(a[1]), float.Parse(a[2])); }
            var wh = resS.Split('x');
            int w = int.Parse(wh[0]), h = int.Parse(wh[1]);

            EditorSceneManager.OpenScene(scenePath, OpenSceneMode.Single);
            var go = new GameObject("SnapCam");
            var cam = go.AddComponent<Camera>();
            go.transform.position = P(posS);
            go.transform.LookAt(P(lookS));
            cam.fieldOfView = float.Parse(fovS);
            cam.farClipPlane = 20000f;
            cam.clearFlags = CameraClearFlags.Skybox;

            var rt = new RenderTexture(w, h, 24);
            cam.targetTexture = rt;
            cam.Render();
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outPath));
            System.IO.File.WriteAllBytes(outPath, tex.EncodeToPNG());
            Debug.Log($"CAPTURE_OK {w}x{h} -> {outPath}");
            EditorApplication.Exit(0);
        }
        catch (System.Exception e) { Debug.LogError("[GltfExporter] CaptureView 异常: " + e); EditorApplication.Exit(1); }
    }

    /// <summary>诊断:打印 prefab 每个 renderer 的 sharedMaterials 与 submesh 数。env: PREFAB_PATH</summary>
    public static void DumpPrefabMaterials()
    {
        var ap = System.Environment.GetEnvironmentVariable("PREFAB_PATH");
        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(ap);
        if (prefab == null) { Debug.LogError("加载失败 " + ap); EditorApplication.Exit(2); return; }
        var inst = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
        foreach (var r in inst.GetComponentsInChildren<Renderer>(true))
        {
            var mf = r.GetComponent<MeshFilter>();
            int sub = mf && mf.sharedMesh ? mf.sharedMesh.subMeshCount : -1;
            Debug.Log($"MATDUMP node={r.gameObject.name} submeshes={sub} mats=[{string.Join(" | ", r.sharedMaterials.Select(m => m ? m.name : "null"))}]");
        }
        Object.DestroyImmediate(inst);
        Debug.Log("MATDUMP_DONE");
        EditorApplication.Exit(0);
    }

    static async void RunExport(GameObject[] roots, string outPath)
    {
        try
        {
            if (roots == null || roots.Length == 0) { Debug.LogError("GLTF_EXPORT_FAIL 无目标节点"); EditorApplication.Exit(1); return; }
            System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outPath));
            var settings = new ExportSettings
            {
                Format = GltfFormat.Binary,
                FileConflictResolution = FileConflictResolution.Overwrite,
                ComponentMask = ~(ComponentType.Camera | ComponentType.Animation),
            };
            var export = new GameObjectExport(settings);
            export.AddScene(roots, "scene");
            bool ok = await export.SaveToFileAndDispose(outPath);
            Debug.Log(ok ? $"GLTF_EXPORT_OK -> {outPath}" : "GLTF_EXPORT_FAIL");
            EditorApplication.Exit(ok ? 0 : 1);
        }
        catch (System.Exception e)
        {
            Debug.LogError("[GltfExporter] 异常: " + e);
            EditorApplication.Exit(1);
        }
    }
}
