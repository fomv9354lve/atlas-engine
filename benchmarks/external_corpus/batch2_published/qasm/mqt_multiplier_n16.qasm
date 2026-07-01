OPENQASM 2.0;
include "qelib1.inc";
gate qft q0,q1,q2,q3,q4,q5,q6,q7 { h q7; cp(pi/2) q7,q6; cp(pi/4) q7,q5; cp(pi/8) q7,q4; cp(pi/16) q7,q3; cp(pi/32) q7,q2; cp(pi/64) q7,q1; cp(0.02454369260617026) q7,q0; h q6; cp(pi/2) q6,q5; cp(pi/4) q6,q4; cp(pi/8) q6,q3; cp(pi/16) q6,q2; cp(pi/32) q6,q1; cp(pi/64) q6,q0; h q5; cp(pi/2) q5,q4; cp(pi/4) q5,q3; cp(pi/8) q5,q2; cp(pi/16) q5,q1; cp(pi/32) q5,q0; h q4; cp(pi/2) q4,q3; cp(pi/4) q4,q2; cp(pi/8) q4,q1; cp(pi/16) q4,q0; h q3; cp(pi/2) q3,q2; cp(pi/4) q3,q1; cp(pi/8) q3,q0; h q2; cp(pi/2) q2,q1; cp(pi/4) q2,q0; h q1; cp(pi/2) q1,q0; h q0; swap q0,q7; swap q1,q6; swap q2,q5; swap q3,q4; }
gate mcphase(param0) q0,q1,q2 { cx q0,q2; rz(-16*pi) q2; cx q1,q2; rz(16*pi) q2; cx q0,q2; rz(-16*pi) q2; cx q1,q2; rz(16*pi) q2; crz(32*pi) q0,q1; p(16*pi) q0; }
gate mcphase_4524868544(param0) q0,q1,q2 { cx q0,q2; rz(-8*pi) q2; cx q1,q2; rz(8*pi) q2; cx q0,q2; rz(-8*pi) q2; cx q1,q2; rz(8*pi) q2; crz(16*pi) q0,q1; p(8*pi) q0; }
gate mcphase_4524869424(param0) q0,q1,q2 { cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; crz(8*pi) q0,q1; p(4*pi) q0; }
gate mcphase_4524869600(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524869776(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524869952(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524870128(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524870304(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524870480(param0) q0,q1,q2 { cx q0,q2; rz(-8*pi) q2; cx q1,q2; rz(8*pi) q2; cx q0,q2; rz(-8*pi) q2; cx q1,q2; rz(8*pi) q2; crz(16*pi) q0,q1; p(8*pi) q0; }
gate mcphase_4524870656(param0) q0,q1,q2 { cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; crz(8*pi) q0,q1; p(4*pi) q0; }
gate mcphase_4524870832(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524871008(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524871184(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524871360(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524871536(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524871712(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524871888(param0) q0,q1,q2 { cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; crz(8*pi) q0,q1; p(4*pi) q0; }
gate mcphase_4524872064(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524872240(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524872416(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524872592(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524872768(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524872944(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524873120(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4524873296(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524873472(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524873648(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524873824(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524874000(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524874176(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524874352(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4524874528(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4524874704(param0) q0,q1,q2 { cx q0,q2; rz(-8*pi) q2; cx q1,q2; rz(8*pi) q2; cx q0,q2; rz(-8*pi) q2; cx q1,q2; rz(8*pi) q2; crz(16*pi) q0,q1; p(8*pi) q0; }
gate mcphase_4524874880(param0) q0,q1,q2 { cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; crz(8*pi) q0,q1; p(4*pi) q0; }
gate mcphase_4524875056(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524875232(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524875408(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524875584(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524875760(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524875936(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524876112(param0) q0,q1,q2 { cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; crz(8*pi) q0,q1; p(4*pi) q0; }
gate mcphase_4524876288(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524876464(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524876640(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524876816(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524876992(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524877168(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524877344(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4524877520(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524877696(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524877872(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524878048(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524878224(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524878400(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524878576(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4524878752(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4524878928(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524879104(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524879280(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524879456(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524879632(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524879808(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4524879984(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4524880160(param0) q0,q1,q2 { cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; crz(pi/64) q0,q1; p(0.02454369260617026) q0; }
gate mcphase_4524880336(param0) q0,q1,q2 { cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; cx q0,q2; rz(-4*pi) q2; cx q1,q2; rz(4*pi) q2; crz(8*pi) q0,q1; p(4*pi) q0; }
gate mcphase_4524880512(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524880688(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524880864(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524881040(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524881216(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524881392(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524881568(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4524881744(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4524881920(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524882096(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524882272(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524882448(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4524882624(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4524882800(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4524882976(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4524883152(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4524883328(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4524883504(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4524883680(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4525097040(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4525097216(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4525097392(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4525097568(param0) q0,q1,q2 { cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; crz(pi/64) q0,q1; p(0.02454369260617026) q0; }
gate mcphase_4525097744(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4525097920(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4525098096(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4525098272(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4525098448(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4525098624(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4525098800(param0) q0,q1,q2 { cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; crz(pi/64) q0,q1; p(0.02454369260617026) q0; }
gate mcphase_4525098976(param0) q0,q1,q2 { cx q0,q2; rz(-0.01227184630308513) q2; cx q1,q2; rz(0.01227184630308513) q2; cx q0,q2; rz(-0.01227184630308513) q2; cx q1,q2; rz(0.01227184630308513) q2; crz(0.02454369260617026) q0,q1; p(0.01227184630308513) q0; }
gate mcphase_4525099152(param0) q0,q1,q2 { cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; cx q0,q2; rz(-2*pi) q2; cx q1,q2; rz(2*pi) q2; crz(4*pi) q0,q1; p(2*pi) q0; }
gate mcphase_4525099328(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4525099504(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4525099680(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4525099856(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4525100032(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4525100208(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4525100384(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4525100560(param0) q0,q1,q2 { cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; cx q0,q2; rz(-pi) q2; cx q1,q2; rz(pi) q2; crz(2*pi) q0,q1; p(pi) q0; }
gate mcphase_4525100736(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4525100912(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4525101088(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4525101264(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4525101440(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4525101616(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4525101792(param0) q0,q1,q2 { cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; crz(pi/64) q0,q1; p(0.02454369260617026) q0; }
gate mcphase_4525101968(param0) q0,q1,q2 { cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; cx q0,q2; rz(-pi/2) q2; cx q1,q2; rz(pi/2) q2; crz(pi) q0,q1; p(pi/2) q0; }
gate mcphase_4525102144(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4525102320(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4525102496(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4525102672(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4525102848(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4525103024(param0) q0,q1,q2 { cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; crz(pi/64) q0,q1; p(0.02454369260617026) q0; }
gate mcphase_4525103200(param0) q0,q1,q2 { cx q0,q2; rz(-0.01227184630308513) q2; cx q1,q2; rz(0.01227184630308513) q2; cx q0,q2; rz(-0.01227184630308513) q2; cx q1,q2; rz(0.01227184630308513) q2; crz(0.02454369260617026) q0,q1; p(0.01227184630308513) q0; }
gate mcphase_4525103376(param0) q0,q1,q2 { cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; cx q0,q2; rz(-pi/4) q2; cx q1,q2; rz(pi/4) q2; crz(pi/2) q0,q1; p(pi/4) q0; }
gate mcphase_4525103552(param0) q0,q1,q2 { cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; cx q0,q2; rz(-pi/8) q2; cx q1,q2; rz(pi/8) q2; crz(pi/4) q0,q1; p(pi/8) q0; }
gate mcphase_4525103728(param0) q0,q1,q2 { cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; cx q0,q2; rz(-pi/16) q2; cx q1,q2; rz(pi/16) q2; crz(pi/8) q0,q1; p(pi/16) q0; }
gate mcphase_4525103904(param0) q0,q1,q2 { cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; cx q0,q2; rz(-pi/32) q2; cx q1,q2; rz(pi/32) q2; crz(pi/16) q0,q1; p(pi/32) q0; }
gate mcphase_4525104080(param0) q0,q1,q2 { cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; cx q0,q2; rz(-pi/64) q2; cx q1,q2; rz(pi/64) q2; crz(pi/32) q0,q1; p(pi/64) q0; }
gate mcphase_4525104256(param0) q0,q1,q2 { cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; cx q0,q2; rz(-0.02454369260617026) q2; cx q1,q2; rz(0.02454369260617026) q2; crz(pi/64) q0,q1; p(0.02454369260617026) q0; }
gate mcphase_4525104432(param0) q0,q1,q2 { cx q0,q2; rz(-0.01227184630308513) q2; cx q1,q2; rz(0.01227184630308513) q2; cx q0,q2; rz(-0.01227184630308513) q2; cx q1,q2; rz(0.01227184630308513) q2; crz(0.02454369260617026) q0,q1; p(0.01227184630308513) q0; }
gate mcphase_4525104608(param0) q0,q1,q2 { cx q0,q2; rz(-0.006135923151542565) q2; cx q1,q2; rz(0.006135923151542565) q2; cx q0,q2; rz(-0.006135923151542565) q2; cx q1,q2; rz(0.006135923151542565) q2; crz(0.01227184630308513) q0,q1; p(0.006135923151542565) q0; }
gate qft_dg q0,q1,q2,q3,q4,q5,q6,q7 { swap q3,q4; swap q2,q5; swap q1,q6; swap q0,q7; h q0; cp(-pi/2) q1,q0; h q1; cp(-pi/4) q2,q0; cp(-pi/2) q2,q1; h q2; cp(-pi/8) q3,q0; cp(-pi/4) q3,q1; cp(-pi/2) q3,q2; h q3; cp(-pi/16) q4,q0; cp(-pi/8) q4,q1; cp(-pi/4) q4,q2; cp(-pi/2) q4,q3; h q4; cp(-pi/32) q5,q0; cp(-pi/16) q5,q1; cp(-pi/8) q5,q2; cp(-pi/4) q5,q3; cp(-pi/2) q5,q4; h q5; cp(-pi/64) q6,q0; cp(-pi/32) q6,q1; cp(-pi/16) q6,q2; cp(-pi/8) q6,q3; cp(-pi/4) q6,q4; cp(-pi/2) q6,q5; h q6; cp(-0.02454369260617026) q7,q0; cp(-pi/64) q7,q1; cp(-pi/32) q7,q2; cp(-pi/16) q7,q3; cp(-pi/8) q7,q4; cp(-pi/4) q7,q5; cp(-pi/2) q7,q6; h q7; }
gate gate_Multiplier q0,q1,q2,q3,q4,q5,q6,q7,q8,q9,q10,q11,q12,q13,q14,q15 { qft q8,q9,q10,q11,q12,q13,q14,q15; mcphase(64*pi) q3,q7,q15; mcphase_4524868544(32*pi) q3,q7,q14; mcphase_4524869424(16*pi) q3,q7,q13; mcphase_4524869600(8*pi) q3,q7,q12; mcphase_4524869776(4*pi) q3,q7,q11; mcphase_4524869952(2*pi) q3,q7,q10; mcphase_4524870128(pi) q3,q7,q9; mcphase_4524870304(pi/2) q3,q7,q8; mcphase_4524870480(32*pi) q3,q6,q15; mcphase_4524870656(16*pi) q3,q6,q14; mcphase_4524870832(8*pi) q3,q6,q13; mcphase_4524871008(4*pi) q3,q6,q12; mcphase_4524871184(2*pi) q3,q6,q11; mcphase_4524871360(pi) q3,q6,q10; mcphase_4524871536(pi/2) q3,q6,q9; mcphase_4524871712(pi/4) q3,q6,q8; mcphase_4524871888(16*pi) q3,q5,q15; mcphase_4524872064(8*pi) q3,q5,q14; mcphase_4524872240(4*pi) q3,q5,q13; mcphase_4524872416(2*pi) q3,q5,q12; mcphase_4524872592(pi) q3,q5,q11; mcphase_4524872768(pi/2) q3,q5,q10; mcphase_4524872944(pi/4) q3,q5,q9; mcphase_4524873120(pi/8) q3,q5,q8; mcphase_4524873296(8*pi) q3,q4,q15; mcphase_4524873472(4*pi) q3,q4,q14; mcphase_4524873648(2*pi) q3,q4,q13; mcphase_4524873824(pi) q3,q4,q12; mcphase_4524874000(pi/2) q3,q4,q11; mcphase_4524874176(pi/4) q3,q4,q10; mcphase_4524874352(pi/8) q3,q4,q9; mcphase_4524874528(pi/16) q3,q4,q8; mcphase_4524874704(32*pi) q2,q7,q15; mcphase_4524874880(16*pi) q2,q7,q14; mcphase_4524875056(8*pi) q2,q7,q13; mcphase_4524875232(4*pi) q2,q7,q12; mcphase_4524875408(2*pi) q2,q7,q11; mcphase_4524875584(pi) q2,q7,q10; mcphase_4524875760(pi/2) q2,q7,q9; mcphase_4524875936(pi/4) q2,q7,q8; mcphase_4524876112(16*pi) q2,q6,q15; mcphase_4524876288(8*pi) q2,q6,q14; mcphase_4524876464(4*pi) q2,q6,q13; mcphase_4524876640(2*pi) q2,q6,q12; mcphase_4524876816(pi) q2,q6,q11; mcphase_4524876992(pi/2) q2,q6,q10; mcphase_4524877168(pi/4) q2,q6,q9; mcphase_4524877344(pi/8) q2,q6,q8; mcphase_4524877520(8*pi) q2,q5,q15; mcphase_4524877696(4*pi) q2,q5,q14; mcphase_4524877872(2*pi) q2,q5,q13; mcphase_4524878048(pi) q2,q5,q12; mcphase_4524878224(pi/2) q2,q5,q11; mcphase_4524878400(pi/4) q2,q5,q10; mcphase_4524878576(pi/8) q2,q5,q9; mcphase_4524878752(pi/16) q2,q5,q8; mcphase_4524878928(4*pi) q2,q4,q15; mcphase_4524879104(2*pi) q2,q4,q14; mcphase_4524879280(pi) q2,q4,q13; mcphase_4524879456(pi/2) q2,q4,q12; mcphase_4524879632(pi/4) q2,q4,q11; mcphase_4524879808(pi/8) q2,q4,q10; mcphase_4524879984(pi/16) q2,q4,q9; mcphase_4524880160(pi/32) q2,q4,q8; mcphase_4524880336(16*pi) q1,q7,q15; mcphase_4524880512(8*pi) q1,q7,q14; mcphase_4524880688(4*pi) q1,q7,q13; mcphase_4524880864(2*pi) q1,q7,q12; mcphase_4524881040(pi) q1,q7,q11; mcphase_4524881216(pi/2) q1,q7,q10; mcphase_4524881392(pi/4) q1,q7,q9; mcphase_4524881568(pi/8) q1,q7,q8; mcphase_4524881744(8*pi) q1,q6,q15; mcphase_4524881920(4*pi) q1,q6,q14; mcphase_4524882096(2*pi) q1,q6,q13; mcphase_4524882272(pi) q1,q6,q12; mcphase_4524882448(pi/2) q1,q6,q11; mcphase_4524882624(pi/4) q1,q6,q10; mcphase_4524882800(pi/8) q1,q6,q9; mcphase_4524882976(pi/16) q1,q6,q8; mcphase_4524883152(4*pi) q1,q5,q15; mcphase_4524883328(2*pi) q1,q5,q14; mcphase_4524883504(pi) q1,q5,q13; mcphase_4524883680(pi/2) q1,q5,q12; mcphase_4525097040(pi/4) q1,q5,q11; mcphase_4525097216(pi/8) q1,q5,q10; mcphase_4525097392(pi/16) q1,q5,q9; mcphase_4525097568(pi/32) q1,q5,q8; mcphase_4525097744(2*pi) q1,q4,q15; mcphase_4525097920(pi) q1,q4,q14; mcphase_4525098096(pi/2) q1,q4,q13; mcphase_4525098272(pi/4) q1,q4,q12; mcphase_4525098448(pi/8) q1,q4,q11; mcphase_4525098624(pi/16) q1,q4,q10; mcphase_4525098800(pi/32) q1,q4,q9; mcphase_4525098976(pi/64) q1,q4,q8; mcphase_4525099152(8*pi) q0,q7,q15; mcphase_4525099328(4*pi) q0,q7,q14; mcphase_4525099504(2*pi) q0,q7,q13; mcphase_4525099680(pi) q0,q7,q12; mcphase_4525099856(pi/2) q0,q7,q11; mcphase_4525100032(pi/4) q0,q7,q10; mcphase_4525100208(pi/8) q0,q7,q9; mcphase_4525100384(pi/16) q0,q7,q8; mcphase_4525100560(4*pi) q0,q6,q15; mcphase_4525100736(2*pi) q0,q6,q14; mcphase_4525100912(pi) q0,q6,q13; mcphase_4525101088(pi/2) q0,q6,q12; mcphase_4525101264(pi/4) q0,q6,q11; mcphase_4525101440(pi/8) q0,q6,q10; mcphase_4525101616(pi/16) q0,q6,q9; mcphase_4525101792(pi/32) q0,q6,q8; mcphase_4525101968(2*pi) q0,q5,q15; mcphase_4525102144(pi) q0,q5,q14; mcphase_4525102320(pi/2) q0,q5,q13; mcphase_4525102496(pi/4) q0,q5,q12; mcphase_4525102672(pi/8) q0,q5,q11; mcphase_4525102848(pi/16) q0,q5,q10; mcphase_4525103024(pi/32) q0,q5,q9; mcphase_4525103200(pi/64) q0,q5,q8; mcphase_4525103376(pi) q0,q4,q15; mcphase_4525103552(pi/2) q0,q4,q14; mcphase_4525103728(pi/4) q0,q4,q13; mcphase_4525103904(pi/8) q0,q4,q12; mcphase_4525104080(pi/16) q0,q4,q11; mcphase_4525104256(pi/32) q0,q4,q10; mcphase_4525104432(pi/64) q0,q4,q9; mcphase_4525104608(0.02454369260617026) q0,q4,q8; qft_dg q8,q9,q10,q11,q12,q13,q14,q15; }
qreg q[16];
creg meas[16];
gate_Multiplier q[0],q[1],q[2],q[3],q[4],q[5],q[6],q[7],q[8],q[9],q[10],q[11],q[12],q[13],q[14],q[15];
barrier q[0],q[1],q[2],q[3],q[4],q[5],q[6],q[7],q[8],q[9],q[10],q[11],q[12],q[13],q[14],q[15];
measure q[0] -> meas[0];
measure q[1] -> meas[1];
measure q[2] -> meas[2];
measure q[3] -> meas[3];
measure q[4] -> meas[4];
measure q[5] -> meas[5];
measure q[6] -> meas[6];
measure q[7] -> meas[7];
measure q[8] -> meas[8];
measure q[9] -> meas[9];
measure q[10] -> meas[10];
measure q[11] -> meas[11];
measure q[12] -> meas[12];
measure q[13] -> meas[13];
measure q[14] -> meas[14];
measure q[15] -> meas[15];