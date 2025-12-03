// draw_event_2x8_overlay.C
//
// 2x8 view + all-channel overlay
// ┌─────────────────────┬─────────────────────────
// │ Canvas1 → Ch0–7 / Ch15–8 (2行×8列)            │
// │ Canvas2 → 16ch 全重ね (TLegend付き)           │
// └─────────────────────┴─────────────────────────
//
// 使い方：
//   root -l dt5742_float_ped.root
//   .L draw_event_2x8_overlay.C+
//   draw_event_2x8_overlay("dt5742_float_ped.root", 12, true);

#include "TFile.h"
#include "TDirectory.h"
#include "TGraph.h"
#include "TCanvas.h"
#include "TLegend.h"
#include "TColor.h"
#include <iostream>

Color_t  colors[16] = {
    kBlack,        // 0
    kRed+1,        // 1
    kBlue+1,       // 2
    kGreen+2,      // 3
    kOrange+7,     // 4
    kMagenta+1,    // 5
    kCyan+1,       // 6
    kYellow+2,     // 7
    kViolet+1,     // 8
    kAzure+4,      // 9
    kPink+6,       // 10
    kTeal+2,       // 11
    kSpring+5,     // 12
    kGray+1,       // 13
    kRed-7,        // 14（ワイン色）
    kBlue-7        // 15（群青）
};

void draw_event_waveforms(const char* filename="wf.root",
			  int event=0, bool usePed=true)
{
    TFile* fin=TFile::Open(filename,"READ");
    if(!fin||fin->IsZombie()){ std::cerr<<"File open error\n"; return; }

    char dname[64];
    sprintf(dname,"event_%06d",event);
    TDirectory* evtDir=(TDirectory*)fin->Get(dname);
    if(!evtDir){ std::cerr<<"No directory "<<dname<<"\n"; return; }

    TString tag = usePed? "ped":"raw";

    //========================================================
    //  Canvas ① → 2x8 view
    //========================================================
    TCanvas* c1 = new TCanvas(Form("evt%d_view",event),
                              Form("Event %d (%s) 2x8 view",event,tag.Data()),
                              1600,700);
    c1->Divide(8,2);

    // 上段 Ch0–7
    for(int ch=0; ch<8; ch++){
        c1->cd(ch+1);
        TGraph* g=(TGraph*)evtDir->Get(Form("ch%02d_%s",ch,tag.Data()));
	g->SetLineColor(kRed+1);	
	g->SetMinimum(1500);	
	g->SetMaximum(4000);
	g->GetXaxis()->SetRangeUser(130,200);
        if(g){ g->SetTitle(Form("Ch%02d",ch)); g->Draw("ALP"); gPad->SetGrid(); }
    }

    // 下段 Ch15–8 (reverse order)
    int pad=8;
    for(int ch=15; ch>=8; ch--){
        c1->cd(++pad);
        TGraph* g=(TGraph*)evtDir->Get(Form("ch%02d_%s",ch,tag.Data()));
	g->SetLineColor(kBlue+1);	
	g->SetMinimum(1500);
	g->SetMaximum(4000);
	g->GetXaxis()->SetRangeUser(130,200);
	if(g){ g->SetTitle(Form("Ch%02d",ch)); g->Draw("ALP"); gPad->SetGrid(); }
    }

    //========================================================
    //  Canvas ② → 全チャンネル重ね描画
    //========================================================
    TCanvas* c2 = new TCanvas(Form("evt%d_overlay",event),
                              Form("Event %d (%s) overlay",event,tag.Data()),
                              1200,700);

    TLegend* leg = new TLegend(0.80,0.2,0.90,0.88);
    leg->SetBorderSize(0); leg->SetTextSize(0.03);

    bool first=true;
    for(int ch=0; ch<16; ch++){
        TGraph* g=(TGraph*)evtDir->Get(Form("ch%02d_%s",ch,tag.Data()));
        if(!g) continue;
	
        Color_t c = 1+ch;               // 色分け
        g->SetLineColor(colors[ch]);
        g->SetLineWidth(2);
	g->SetMinimum(1500);
	g->SetMaximum(4000);
        if(first){ g->Draw("AL"); first=false; }
        else      g->Draw("L SAME");

        leg->AddEntry(g,Form("Ch%02d",ch),"l");
    }

    leg->Draw();
    c2->Update();
}
