using System;
using System.IO;
using Qa59Installed;
using Qa59Installed.Runtime;

internal static class RunnerCandidateTests
{
    private static int checks,failed;
    private const string Qa="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private static readonly string Msi=new string('b',64);
    private static void Check(bool ok) { checks++; if(!ok) failed++; }
    private static JsonMap Document()
    {
        return new JsonMap {
            {"schema",1L},{"kind",RunnerCandidate.Kind},{"source_head",CandidatePins.ProductHead},{"qa_head",Qa},{"run_id",42L},
            {"origin","FRESH_HOSTED_SOURCE"},{"source_clean",true},{"original_candidate",false},{"msi_sha256",Msi},{"msi_size_bytes",123L},
            {"desktop_sha256",new string('c',64)},{"core_sha256",new string('d',64)},{"ffmpeg_sha256",new string('e',64)},{"manifest_sha256",new string('f',64)} };
    }
    private static RunnerCandidate Validate(JsonMap doc,string observed=null,long size=123,string qa=Qa,long run=42)
    { return RunnerCandidate.Validate(doc.Text(),observed??Msi,size,qa,run,new Outcome()); }
    public static int Main(string[] args)
    {
        Check(Validate(Document())!=null);
        foreach(var change in new object[][] {
            new object[]{"schema",2L},new object[]{"kind","QA59_CANDIDATE_MANIFEST"},new object[]{"origin","LOCAL_MSI"},
            new object[]{"source_head",Qa},new object[]{"source_clean",false},new object[]{"original_candidate",true},
            new object[]{"qa_head",new string('c',40)},new object[]{"run_id",43L},new object[]{"msi_sha256",new string('a',64)},
            new object[]{"msi_size_bytes",124L},new object[]{"desktop_sha256","SECRET"},new object[]{"core_sha256","C:\\private"},
            new object[]{"ffmpeg_sha256",new string('A',64)},new object[]{"manifest_sha256",new string('a',63)} })
        { var doc=Document(); doc[(string)change[0]]=change[1]; Check(Validate(doc)==null); }
        var extra=Document();extra.Add("execution_allowed",true);Check(Validate(extra)==null);
        var missing=Document();missing.Remove("original_candidate");Check(Validate(missing)==null);
        Check(Validate(Document(),new string('a',64))==null);
        Check(Validate(Document(),size:0)==null);
        Check(Validate(Document(),qa:CandidatePins.ProductHead)==null);
        Check(Validate(Document(),qa:null)==null);
        Check(Validate(Document(),run:0)==null);
        var candidate=Validate(Document());
        Check(candidate!=null&&candidate.RunId==42&&candidate.MsiHash==Msi&&candidate.MsiSize==123);
        Check(!ContextGate.Evaluate("{}").MsiInstallAllowed);
        if(args.Length==1)
        {
            var original=CandidateManifest.Validate(File.ReadAllText(Path.Combine(args[0],"candidate-manifest.json")),new Outcome());
            Check(original!=null&&Observation.Msi(original,Msi,123)==Verdict.FAIL);
            Check(!InstallerPermit.MayInvokeMsiexec(original,Verdict.PASS,ContextGate.Evaluate("{}")));
        }
        Console.WriteLine("RUNNER_CANDIDATE_TESTS checks="+checks+" failed="+failed);
        return failed==0?0:1;
    }
}
